"""GitHub repository audit endpoint — clone a repo, extract .sol files, trigger audit."""
from __future__ import annotations

import io
import os
import re
import subprocess
import tarfile
import tempfile
import uuid
import zipfile
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.const import ALLOWED_MODELS
from api.core.deps import OptionalTokenDep, get_db
from api.core.rabbitmq import RabbitMQPublisher, get_rabbitmq_publisher
from api.models.job import Job, JobStatus
from api.secrets.impl import secret_storage


DEFAULT_MODEL = 'gpt-5.2-codex'


router = APIRouter(prefix='/github', tags=['github'])

DbSessionDep = Annotated[AsyncSession, Depends(get_db)]
PublisherDep = Annotated[RabbitMQPublisher, Depends(get_rabbitmq_publisher)]

GITHUB_URL_RE = re.compile(
    r'(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.+))?)?$',
)


class GitHubAuditRequest(BaseModel):
    url: str
    model: str | None = None


class GitHubAuditResponse(BaseModel):
    job_id: str
    cached: bool


def _parse_github_url(url: str) -> tuple[str, str, str | None, str | None]:
    """Parse GitHub URL into (owner, repo, branch, path)."""
    m = GITHUB_URL_RE.match(url.strip().rstrip('/'))
    if not m:
        raise HTTPException(status_code=400, detail='Invalid GitHub URL')
    owner = m.group(1)
    repo = m.group(2)
    branch = m.group(3)  # None if not /tree/branch
    path = m.group(4)    # None if no subpath
    return owner, repo, branch, path


def _clone_and_zip(clone_url: str, branch: str | None, subpath: str | None) -> bytes:
    """Shallow-clone repo, find .sol files, zip them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = ['git', 'clone', '--depth=1']
        if branch:
            cmd.extend(['--branch', branch])
        cmd.extend([clone_url, tmpdir + '/repo'])

        result = subprocess.run(cmd, capture_output=True, timeout=120, check=False)  # noqa: S603
        if result.returncode != 0:
            detail = result.stderr.decode(errors='replace')[:200] if result.stderr else 'Unknown error'
            raise HTTPException(status_code=400, detail=f'Failed to clone repository: {detail}')

        repo_path = Path(tmpdir) / 'repo'
        search_path = repo_path / subpath if subpath else repo_path
        if not search_path.exists():
            raise HTTPException(status_code=400, detail=f'Path {subpath} not found in repository')

        sol_files = list(search_path.rglob('*.sol'))
        if not sol_files:
            raise HTTPException(status_code=400, detail='No Solidity files found in repository')

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in sol_files:
                zf.write(f, str(f.relative_to(repo_path)))
        return buf.getvalue()


@router.post('/audit', response_model=GitHubAuditResponse)
async def audit_github_repo(
    body: GitHubAuditRequest,
    session: DbSessionDep,
    publisher: PublisherDep,
    token: OptionalTokenDep,
) -> GitHubAuditResponse:
    """Clone a GitHub repo, extract Solidity files, and trigger an audit."""
    owner, repo, branch, subpath = _parse_github_url(body.url)
    tag = f'github:{owner}/{repo}'
    user_id = token.user_id if token else 'github'
    model = body.model or DEFAULT_MODEL
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f'Invalid model: {model}')

    # Check for cached successful result (within 24h) for this model
    since = datetime.now(UTC) - timedelta(hours=24)
    existing = await session.scalar(
        select(Job)
        .where(Job.file_name == tag, Job.model == model, Job.status == JobStatus.succeeded, Job.created_at >= since)
        .order_by(Job.created_at.desc())
        .limit(1),
    )
    if existing:
        return GitHubAuditResponse(job_id=str(existing.id), cached=True)

    # Check for in-progress scan for this model
    in_progress = await session.scalar(
        select(Job)
        .where(Job.file_name == tag, Job.model == model, Job.status.in_([JobStatus.queued, JobStatus.running]))
        .limit(1),
    )
    if in_progress:
        return GitHubAuditResponse(job_id=str(in_progress.id), cached=False)

    # Clone and zip
    clone_url = f'https://github.com/{owner}/{repo}.git'
    zip_bytes = _clone_and_zip(clone_url, branch, subpath)

    # Determine credentials for the worker (same logic as permalink.py)
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
            detail='GitHub auditing requires a preconfigured API key or subscription mode',
        )

    job_id = uuid.uuid4()
    secret_ref = os.urandom(32).hex()
    result_token = os.urandom(32).hex()

    # Build bundle (same as permalink.py)
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
        user_id=user_id,
        secret_ref=secret_ref,
        result_token=result_token,
        model=model,
        file_name=tag,
        public=True,
    )
    session.add(job)
    await session.commit()

    try:
        await publisher.publish_job_start(
            job_id=str(job_id),
            secret_ref=secret_ref,
            model=model,
            result_token=result_token,
        )
    except Exception as err:
        with suppress(Exception):
            await secret_storage.delete_secret(secret_ref)
        await session.delete(job)
        await session.commit()
        raise HTTPException(status_code=502, detail='Failed to enqueue job') from err

    return GitHubAuditResponse(job_id=str(job_id), cached=False)
