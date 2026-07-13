"""Permalink auditing — fetch source from Snowtrace and trigger an audit."""
from __future__ import annotations

import io
import os
import posixpath
import re
import tarfile
import uuid
import zipfile
from contextlib import suppress
from typing import Annotated, Literal

import httpx
import orjson
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.const import ALLOWED_MODELS
from api.core.deps import get_db
from api.core.rabbitmq import RabbitMQPublisher, get_rabbitmq_publisher
from api.models.job import Job, JobStatus
from api.secrets.impl import secret_storage


DEFAULT_MODEL = 'gpt-5.2-codex'


router = APIRouter(prefix='/permalink', tags=['permalink'])

DbSessionDep = Annotated[AsyncSession, Depends(get_db)]
PublisherDep = Annotated[RabbitMQPublisher, Depends(get_rabbitmq_publisher)]

AVALANCHE_ADDRESS_RE = re.compile(r'^0x[0-9a-fA-F]{40}$')

CHAIN_CONFIGS = {
    'avalanche': {
        'api_url': 'https://api.snowtrace.io/api',
        'name': 'Avalanche C-Chain',
    },
    'fuji': {
        'api_url': 'https://api-testnet.snowtrace.io/api',
        'name': 'Avalanche Fuji Testnet',
    },
}


class PermalinkResult(BaseModel):
    status: Literal['cached', 'scanning', 'source_not_available']
    job_id: str | None = None
    result: dict | None = None


async def _fetch_source_from_snowtrace(chain: str, address: str, api_key: str | None = None) -> dict[str, str] | None:
    """Fetch verified source from Snowtrace API. Returns {filename: source} or None."""
    config = CHAIN_CONFIGS.get(chain)
    if not config:
        return None

    params = {
        'module': 'contract',
        'action': 'getsourcecode',
        'address': address,
    }
    if api_key:
        params['apikey'] = api_key
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(config['api_url'], params=params)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return None

    if data.get('status') != '1' or not data.get('result'):
        return None

    result = data['result'][0]
    source_code = result.get('SourceCode', '')
    contract_name = result.get('ContractName', 'Contract') or 'Contract'

    if not source_code:
        return None

    files: dict[str, str] = {}
    # Multi-file source (wrapped in {{ }})
    if source_code.startswith('{{'):
        try:
            inner = source_code[1:-1]
            parsed = orjson.loads(inner)
            for fname, content in parsed.get('sources', {}).items():
                files[fname] = content.get('content', '')
        except (ValueError, KeyError):
            files[f'{contract_name}.sol'] = source_code
    elif source_code.startswith('{'):
        try:
            parsed = orjson.loads(source_code)
            for fname, content in parsed.get('sources', {}).items():
                files[fname] = content.get('content', '')
        except (ValueError, KeyError):
            files[f'{contract_name}.sol'] = source_code
    else:
        files[f'{contract_name}.sol'] = source_code

    return files or None


def _sanitize_filename(name: str) -> str:
    """Strip path traversal from external filenames."""
    # Normalize and remove leading slashes, backslashes, and .. segments
    normalized = posixpath.normpath(name).replace('\\', '/')
    parts = [p for p in normalized.split('/') if p and p != '..']
    return '/'.join(parts) or 'contract.sol'


def _create_zip_from_sources(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, content in files.items():
            safe_name = _sanitize_filename(fname)
            zf.writestr(safe_name, content)
    return buf.getvalue()


@router.get('/{chain}/{address}', response_model=PermalinkResult)
async def get_permalink(
    chain: str,
    address: str,
    session: DbSessionDep,
    publisher: PublisherDep,
    model: str | None = None,
) -> PermalinkResult:
    if chain not in CHAIN_CONFIGS:
        raise HTTPException(status_code=400, detail=f'Unsupported chain: {chain}')
    if not AVALANCHE_ADDRESS_RE.match(address):
        raise HTTPException(status_code=400, detail='Invalid Avalanche address')
    selected_model = model or DEFAULT_MODEL
    if selected_model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f'Invalid model: {selected_model}')

    # Check for cached result for this model
    tag = f'permalink:{chain}:{address.lower()}'
    existing = await session.scalar(
        select(Job)
        .where(Job.file_name == tag, Job.model == selected_model, Job.status == JobStatus.succeeded)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    if existing:
        return PermalinkResult(status='cached', job_id=str(existing.id), result=existing.result)

    # Check for in-progress scan for this model
    in_progress = await session.scalar(
        select(Job)
        .where(Job.file_name == tag, Job.model == selected_model, Job.status.in_([JobStatus.queued, JobStatus.running]))
        .limit(1)
    )
    if in_progress:
        return PermalinkResult(status='scanning', job_id=str(in_progress.id))

    # Fetch source from Snowtrace
    api_key = settings.SNOWTRACE_API_KEY.get_secret_value() if settings.SNOWTRACE_API_KEY else None
    source_files = await _fetch_source_from_snowtrace(chain, address, api_key=api_key)
    if not source_files:
        return PermalinkResult(status='source_not_available')

    # Trigger new audit
    zip_bytes = _create_zip_from_sources(source_files)

    # Determine credentials for the worker
    if settings.BACKEND_OAI_KEY_MODE == 'subscription':
        openai_token = ''
        key_mode = 'subscription'
    elif settings.BACKEND_USE_PROXY_STATIC_KEY:
        openai_token = 'STATIC'  # noqa: S105
        key_mode = 'proxy_static'
    elif settings.BACKEND_STATIC_OAI_KEY:
        openai_token = settings.BACKEND_STATIC_OAI_KEY.get_secret_value()
        key_mode = 'direct'
    else:
        raise HTTPException(
            status_code=412,
            detail='Permalink auditing requires a preconfigured API key or subscription mode',
        )

    job_id = uuid.uuid4()
    secret_ref = os.urandom(32).hex()
    result_token = os.urandom(32).hex()

    # Build bundle from raw bytes
    zip_io = io.BytesIO(zip_bytes)
    key_payload = orjson.dumps({'openai_token': openai_token, 'key_mode': key_mode})
    bundle_buf = io.BytesIO()
    with tarfile.open(fileobj=bundle_buf, mode='w') as tar:
        zi = tarfile.TarInfo(name='upload.zip')
        zi.size = len(zip_bytes)
        tar.addfile(zi, fileobj=zip_io)
        ki = tarfile.TarInfo(name='key.json')
        ki.size = len(key_payload)
        tar.addfile(ki, fileobj=io.BytesIO(key_payload))
    bundle = bundle_buf.getvalue()

    await secret_storage.save_secret(secret_ref, bundle)

    job = Job(
        id=job_id,
        status=JobStatus.queued,
        user_id='permalink',
        secret_ref=secret_ref,
        result_token=result_token,
        model=selected_model,
        file_name=tag,
        public=True,
    )
    session.add(job)
    await session.commit()

    try:
        await publisher.publish_job_start(
            job_id=str(job_id),
            secret_ref=secret_ref,
            model=selected_model,
            result_token=result_token,
        )
    except Exception as err:
        with suppress(Exception):
            await secret_storage.delete_secret(secret_ref)
        await session.delete(job)
        await session.commit()
        raise HTTPException(status_code=502, detail='Failed to enqueue job') from err

    return PermalinkResult(status='scanning', job_id=str(job_id))
