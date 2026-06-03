"""
GitHub App bot webhook handler.
Listens for PR events, triggers audits, posts review comments.
"""
import hashlib
import hmac
import io
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import ORJSONResponse


GITHUB_WEBHOOK_SECRET = os.getenv('GHBOT_WEBHOOK_SECRET', '')
GITHUB_APP_TOKEN = os.getenv('GHBOT_APP_TOKEN', '')
BACKEND_URL = os.getenv('GHBOT_BACKEND_URL', 'http://backend:1337')
GHBOT_HOST = os.getenv('GHBOT_HOST', '0.0.0.0')
GHBOT_PORT = int(os.getenv('GHBOT_PORT', '8085'))

app = FastAPI(title='avaxbench-ghbot', default_response_class=ORJSONResponse)


def _verify_signature(body: bytes, signature: str) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        return True
    expected = 'sha256=' + hmac.new(  # type: ignore[attr-defined]
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _clone_and_zip(repo_clone_url: str, ref: str) -> bytes | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ['git', 'clone', '--depth=1', '--branch', ref, repo_clone_url, tmpdir + '/repo'],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            return None

        repo_path = Path(tmpdir) / 'repo'
        sol_files = list(repo_path.rglob('*.sol'))
        if not sol_files:
            return None

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for sol_file in sol_files:
                arcname = str(sol_file.relative_to(repo_path))
                zf.write(sol_file, arcname)
        return buf.getvalue()


async def _post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> None:
    if not GITHUB_APP_TOKEN:
        return
    async with httpx.AsyncClient() as client:
        await client.post(
            f'https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments',
            headers={'Authorization': f'Bearer {GITHUB_APP_TOKEN}', 'Accept': 'application/vnd.github+json'},
            json={'body': body},
        )


@app.post('/webhook')
async def handle_webhook(
    request: Request,
    x_github_event: str = Header(default=''),  # noqa: FAST002
    x_hub_signature_256: str = Header(default=''),  # noqa: FAST002
) -> dict:
    body = await request.body()

    if GITHUB_WEBHOOK_SECRET and not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail='Invalid signature')

    if x_github_event != 'pull_request':
        return {'status': 'ignored'}

    payload = json.loads(body)
    action = payload.get('action')
    if action not in ('opened', 'synchronize'):
        return {'status': 'ignored'}

    pr = payload.get('pull_request', {})
    repo = payload.get('repository', {})
    pr_number = pr.get('number')
    head_ref = pr.get('head', {}).get('ref', '')
    clone_url = repo.get('clone_url', '')
    repo_full_name = repo.get('full_name', '')

    if not clone_url or not pr_number:
        return {'status': 'missing fields'}

    # Clone and zip Solidity files
    zip_bytes = await _clone_and_zip(clone_url, head_ref)
    if not zip_bytes:
        return {'status': 'no solidity files'}

    # Trigger audit via backend
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f'{BACKEND_URL}/v1/jobs/start',
            files={'file': ('pr.zip', zip_bytes, 'application/zip')},
            data={'model': 'codex-gpt-5.2'},
        )
        if r.status_code != 200:
            return {'status': 'audit trigger failed'}
        job_data = r.json()
        job_id = job_data.get('job_id')

    await _post_pr_comment(
        repo_full_name, pr_number,
        f'**AvaxBench Security Scan** started.\n\nAudit ID: `{job_id}`\n\n'
        f'Results will be posted when the scan completes (~5-60 min depending on contract size).',
    )

    return {'status': 'triggered', 'job_id': job_id}


def main() -> None:
    uvicorn.run(app, host=GHBOT_HOST, port=GHBOT_PORT, server_header=False)


if __name__ == '__main__':
    main()
