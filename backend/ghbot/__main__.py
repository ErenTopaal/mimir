"""
GitHub App bot webhook handler.

Listens for PR events, triggers AvaxBench security audits on changed Solidity
files, creates GitHub Check Runs, posts inline review comments with
vulnerability findings, and updates the original PR comment with results.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import ORJSONResponse
from loguru import logger


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_WEBHOOK_SECRET = os.getenv('GHBOT_WEBHOOK_SECRET', '')
BACKEND_URL = os.getenv('GHBOT_BACKEND_URL', 'http://backend:1337')
GHBOT_HOST = os.getenv('GHBOT_HOST', '0.0.0.0')
GHBOT_PORT = int(os.getenv('GHBOT_PORT', '8085'))

# GitHub App auth (preferred)
GHBOT_APP_ID = os.getenv('GHBOT_APP_ID', '')
GHBOT_PRIVATE_KEY_PATH = os.getenv('GHBOT_PRIVATE_KEY_PATH', '')
GHBOT_INSTALLATION_ID = os.getenv('GHBOT_INSTALLATION_ID', '')

# Legacy fallback: static personal access token
GHBOT_APP_TOKEN = os.getenv('GHBOT_APP_TOKEN', '')

GITHUB_API = 'https://api.github.com'

# Polling configuration
POLL_INTERVAL_SECONDS = 30
POLL_MAX_ATTEMPTS = 60

# ---------------------------------------------------------------------------
# Installation token cache
# ---------------------------------------------------------------------------

_token_cache: dict[str, Any] = {
    'token': None,
    'expires_at': 0.0,
}

# Strong references to background tasks so they aren't garbage-collected.
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

app = FastAPI(title='avaxbench-ghbot', default_response_class=ORJSONResponse)


# ---------------------------------------------------------------------------
# GitHub App JWT & installation token helpers
# ---------------------------------------------------------------------------


def _create_app_jwt() -> str:
    """Create a short-lived JWT signed with the GitHub App private key."""
    private_key = Path(GHBOT_PRIVATE_KEY_PATH).read_text()
    now = int(time.time())
    payload = {
        'iss': GHBOT_APP_ID,
        'iat': now - 60,
        'exp': now + 600,
    }
    return jwt.encode(payload, private_key, algorithm='RS256')


async def _get_installation_token() -> str | None:
    """Return a valid GitHub installation token, caching until near-expiry.

    Falls back to the static ``GHBOT_APP_TOKEN`` env var when App-based
    authentication is not configured.
    """
    # Fall back to static token when App credentials are absent.
    if not GHBOT_APP_ID or not GHBOT_PRIVATE_KEY_PATH or not GHBOT_INSTALLATION_ID:
        return GHBOT_APP_TOKEN or None

    # Return cached token if still valid (5 min safety margin).
    if _token_cache['token'] and time.time() < _token_cache['expires_at'] - 300:
        return _token_cache['token']

    app_jwt = _create_app_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{GITHUB_API}/app/installations/{GHBOT_INSTALLATION_ID}/access_tokens',
            headers={
                'Authorization': f'Bearer {app_jwt}',
                'Accept': 'application/vnd.github+json',
            },
        )
        if resp.status_code != 201:
            logger.error('Failed to get installation token: {} {}', resp.status_code, resp.text)
            return GHBOT_APP_TOKEN or None

        data = resp.json()
        _token_cache['token'] = data['token']
        # GitHub returns ISO-8601 expiry; parse to epoch.
        expires_str = data.get('expires_at', '')
        try:
            dt = datetime.fromisoformat(expires_str)
            _token_cache['expires_at'] = dt.timestamp()
        except (ValueError, AttributeError):
            # Conservative fallback: expire in 50 minutes.
            _token_cache['expires_at'] = time.time() + 3000

        logger.info('Obtained new GitHub installation token (expires {})', expires_str)
        return _token_cache['token']


async def _github_headers() -> dict[str, str]:
    """Return standard headers for authenticated GitHub API requests."""
    token = await _get_installation_token()
    headers: dict[str, str] = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def _verify_signature(body: bytes, signature: str) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        return False
    expected = 'sha256=' + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# PR diff analysis
# ---------------------------------------------------------------------------


async def _get_changed_sol_files(owner: str, repo: str, pr_number: int) -> list[str]:
    """Return list of ``.sol`` file paths changed in the given PR."""
    headers = await _github_headers()
    sol_files: list[str] = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f'{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files',
                headers=headers,
                params={'per_page': 100, 'page': page},
            )
            if resp.status_code != 200:
                logger.warning('Failed to list PR files: {} {}', resp.status_code, resp.text)
                break

            files = resp.json()
            if not files:
                break

            for f in files:
                filename = f.get('filename', '')
                if filename.endswith('.sol'):
                    sol_files.append(filename)

            if len(files) < 100:
                break
            page += 1

    return sol_files


# ---------------------------------------------------------------------------
# Clone + ZIP helpers
# ---------------------------------------------------------------------------


async def _clone_and_zip(repo_clone_url: str, ref: str, *, file_filter: set[str] | None = None) -> bytes | None:
    """Clone the repo at *ref* and zip Solidity files.

    When *file_filter* is provided, only files whose relative path appears in
    the filter set are included in the resulting archive.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ['git', 'clone', '--depth=1', '--branch', ref, repo_clone_url, tmpdir + '/repo'],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            logger.warning('git clone failed: {}', result.stderr.decode(errors='replace')[:500])
            return None

        repo_path = Path(tmpdir) / 'repo'
        sol_files = list(repo_path.rglob('*.sol'))
        if not sol_files:
            return None

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for sol_file in sol_files:
                arcname = str(sol_file.relative_to(repo_path))
                if file_filter is not None and arcname not in file_filter:
                    continue
                zf.write(sol_file, arcname)

        # If filter removed everything, return None.
        if buf.tell() == 0:
            return None
        return buf.getvalue()


# ---------------------------------------------------------------------------
# GitHub PR comment helpers
# ---------------------------------------------------------------------------


async def _post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> int | None:
    """Post a comment on a PR and return the comment ID."""
    headers = await _github_headers()
    if 'Authorization' not in headers:
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{GITHUB_API}/repos/{repo_full_name}/issues/{pr_number}/comments',
            headers=headers,
            json={'body': body},
        )
        if resp.status_code == 201:
            return resp.json().get('id')
        logger.warning('Failed to post PR comment: {} {}', resp.status_code, resp.text)
        return None


async def _update_pr_comment(repo_full_name: str, comment_id: int, body: str) -> None:
    """Edit an existing PR comment."""
    headers = await _github_headers()
    if 'Authorization' not in headers:
        return

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f'{GITHUB_API}/repos/{repo_full_name}/issues/comments/{comment_id}',
            headers=headers,
            json={'body': body},
        )
        if resp.status_code != 200:
            logger.warning('Failed to update PR comment: {} {}', resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# GitHub Check Run helpers
# ---------------------------------------------------------------------------


async def _create_check_run(repo_full_name: str, head_sha: str) -> int | None:
    """Create an in-progress check run and return its ID."""
    headers = await _github_headers()
    if 'Authorization' not in headers:
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{GITHUB_API}/repos/{repo_full_name}/check-runs',
            headers=headers,
            json={
                'name': 'AvaxBench Security Scan',
                'head_sha': head_sha,
                'status': 'in_progress',
            },
        )
        if resp.status_code == 201:
            return resp.json().get('id')
        logger.warning('Failed to create check run: {} {}', resp.status_code, resp.text)
        return None


async def _update_check_run(
    repo_full_name: str,
    check_run_id: int,
    *,
    status: str = 'completed',
    conclusion: str = 'success',
    title: str = 'AvaxBench Security Scan',
    summary: str = '',
) -> None:
    """Update an existing check run with conclusion and summary."""
    headers = await _github_headers()
    if 'Authorization' not in headers:
        return

    payload: dict[str, Any] = {
        'status': status,
        'conclusion': conclusion,
        'output': {
            'title': title,
            'summary': summary,
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f'{GITHUB_API}/repos/{repo_full_name}/check-runs/{check_run_id}',
            headers=headers,
            json=payload,
        )
        if resp.status_code != 200:
            logger.warning('Failed to update check run: {} {}', resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# Inline PR review comments
# ---------------------------------------------------------------------------


async def _post_review_comments(
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    vulns: list[dict[str, Any]],
) -> None:
    """Post inline review comments on the PR for each vulnerability."""
    comments: list[dict[str, Any]] = []

    for vuln in vulns:
        file_path = vuln.get('file') or vuln.get('path')
        line_start = vuln.get('line_start') or vuln.get('line')
        if not file_path or not line_start:
            continue

        severity = vuln.get('severity', 'INFO')
        title = vuln.get('title', 'Finding')
        desc = vuln.get('description', vuln.get('desc', ''))

        body = f'**{severity}** \u2014 {title}'
        if desc:
            body += f'\n\n{desc}'

        comments.append({
            'path': file_path,
            'line': int(line_start),
            'body': body,
        })

    if not comments:
        return

    headers = await _github_headers()
    if 'Authorization' not in headers:
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews',
            headers=headers,
            json={
                'commit_id': head_sha,
                'event': 'COMMENT',
                'comments': comments,
            },
        )
        if resp.status_code not in (200, 201):
            logger.warning('Failed to post review comments: {} {}', resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# Severity summary formatting
# ---------------------------------------------------------------------------


def _build_severity_table(vulns: list[dict[str, Any]]) -> str:
    """Build a Markdown severity summary table from vulnerability entries."""
    counts: dict[str, int] = {}
    for v in vulns:
        sev = v.get('severity', 'UNKNOWN').upper()
        counts[sev] = counts.get(sev, 0) + 1

    severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', 'UNKNOWN']
    lines = ['| Severity | Count |', '|----------|-------|']
    total = 0
    for sev in severity_order:
        if sev in counts:
            lines.append(f'| {sev} | {counts[sev]} |')
            total += counts[sev]

    # Include any severity levels not in the predefined order.
    for sev, count in sorted(counts.items()):
        if sev not in severity_order:
            lines.append(f'| {sev} | {count} |')
            total += count

    lines.append(f'| **Total** | **{total}** |')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Result polling + finalization
# ---------------------------------------------------------------------------


async def _poll_and_finalize(
    *,
    job_id: str,
    repo_full_name: str,
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    comment_id: int | None,
    check_run_id: int | None,
) -> None:
    """Poll the backend for audit results and finalize GitHub artifacts.

    This function is launched as a background ``asyncio.Task`` so as not to
    block the webhook HTTP response.
    """
    logger.info('Polling job {} for PR #{} on {}', job_id, pr_number, repo_full_name)

    final_status: str | None = None
    result_data: dict[str, Any] | None = None
    error_msg: str | None = None

    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f'{BACKEND_URL}/v1/jobs/{job_id}')
                if resp.status_code != 200:
                    logger.debug('Poll attempt {}: HTTP {}', attempt, resp.status_code)
                    continue

                data = resp.json()
                status = data.get('status', '')

                if status == 'succeeded':
                    final_status = 'succeeded'
                    result_data = data.get('result') or {}
                    break
                if status == 'failed':
                    final_status = 'failed'
                    error_msg = data.get('error') or 'Audit failed with no additional details.'
                    break
                # Still running / queued — keep polling.
                logger.debug('Poll attempt {}: status={}', attempt, status)

        except Exception:
            logger.exception('Error polling job {} (attempt {})', job_id, attempt)

    # ------- Handle timeout -------
    if final_status is None:
        final_status = 'timeout'
        error_msg = 'Audit timed out after polling for the maximum duration.'

    # ------- Extract vulnerabilities -------
    vulns: list[dict[str, Any]] = []
    if result_data:
        # Support various result shapes.
        vulns = result_data.get('vulnerabilities', result_data.get('findings', []))
        if not isinstance(vulns, list):
            vulns = []

    # ------- Update PR comment -------
    if comment_id is not None:
        if final_status == 'succeeded':
            severity_table = _build_severity_table(vulns)
            body = (
                f'**AvaxBench Security Scan** \u2014 completed \u2705\n\n'
                f'Audit ID: `{job_id}`\n\n'
                f'{severity_table}\n\n'
                f'[View full report]({BACKEND_URL.rstrip("/")}/results/{job_id})'
            )
            await _update_pr_comment(repo_full_name, comment_id, body)
        else:
            body = (
                f'**AvaxBench Security Scan** \u2014 failed \u274c\n\n'
                f'Audit ID: `{job_id}`\n\n'
                f'Error: {error_msg}'
            )
            await _update_pr_comment(repo_full_name, comment_id, body)

    # ------- Update check run -------
    if check_run_id is not None:
        if final_status == 'succeeded':
            has_critical = any(v.get('severity', '').upper() in ('CRITICAL', 'HIGH') for v in vulns)
            conclusion = 'failure' if has_critical else 'success'
            summary = _build_severity_table(vulns) if vulns else 'No vulnerabilities found.'
            await _update_check_run(
                repo_full_name, check_run_id,
                conclusion=conclusion,
                title='AvaxBench Security Scan',
                summary=summary,
            )
        else:
            await _update_check_run(
                repo_full_name, check_run_id,
                conclusion='failure',
                title='AvaxBench Security Scan',
                summary=error_msg or 'Unknown failure.',
            )

    # ------- Post inline review comments -------
    if final_status == 'succeeded' and vulns:
        await _post_review_comments(owner, repo, pr_number, head_sha, vulns)

    logger.info('Finalized job {} for PR #{}: {}', job_id, pr_number, final_status)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


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
    repo_payload = payload.get('repository', {})
    pr_number = pr.get('number')
    head_ref = pr.get('head', {}).get('ref', '')
    head_sha = pr.get('head', {}).get('sha', '')
    clone_url = repo_payload.get('clone_url', '')
    repo_full_name = repo_payload.get('full_name', '')
    owner = repo_payload.get('owner', {}).get('login', '')
    repo_name = repo_payload.get('name', '')

    if not clone_url or not pr_number:
        return {'status': 'missing fields'}

    # ---- Check which Solidity files changed ----
    changed_sol = await _get_changed_sol_files(owner, repo_name, pr_number)
    if not changed_sol:
        await _post_pr_comment(
            repo_full_name, pr_number,
            'No Solidity files changed in this PR.',
        )
        return {'status': 'no solidity changes'}

    logger.info('PR #{} on {} has {} changed .sol files', pr_number, repo_full_name, len(changed_sol))

    # ---- Create check run ----
    check_run_id = await _create_check_run(repo_full_name, head_sha)

    # ---- Clone and zip (only changed Solidity files) ----
    zip_bytes = await _clone_and_zip(clone_url, head_ref, file_filter=set(changed_sol))
    if not zip_bytes:
        await _post_pr_comment(
            repo_full_name, pr_number,
            '**AvaxBench Security Scan** \u2014 could not collect Solidity files from this PR.',
        )
        if check_run_id is not None:
            await _update_check_run(
                repo_full_name, check_run_id,
                conclusion='cancelled',
                summary='No Solidity files could be collected from the PR branch.',
            )
        return {'status': 'no solidity files'}

    # ---- Trigger audit via backend ----
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f'{BACKEND_URL}/v1/jobs/start',
            files={'file': ('pr.zip', zip_bytes, 'application/zip')},
            data={'model': 'gpt-5.2-codex'},
        )
        if r.status_code != 200:
            logger.error('Audit trigger failed: {} {}', r.status_code, r.text)
            if check_run_id is not None:
                await _update_check_run(
                    repo_full_name, check_run_id,
                    conclusion='failure',
                    summary='Failed to start the security audit.',
                )
            return {'status': 'audit trigger failed'}

        job_data = r.json()
        job_id = job_data.get('job_id')
        if not job_id or not isinstance(job_id, str):
            return {'status': 'audit trigger failed', 'reason': 'invalid job_id'}

    # ---- Post initial PR comment ----
    comment_id = await _post_pr_comment(
        repo_full_name, pr_number,
        f'**AvaxBench Security Scan** started \u23f3\n\n'
        f'Audit ID: `{job_id}`\n\n'
        f'Results will be posted when the scan completes (~5\u201360 min depending on contract size).',
    )

    # ---- Launch background polling task ----
    task = asyncio.create_task(
        _poll_and_finalize(
            job_id=job_id,
            repo_full_name=repo_full_name,
            owner=owner,
            repo=repo_name,
            pr_number=pr_number,
            head_sha=head_sha,
            comment_id=comment_id,
            check_run_id=check_run_id,
        ),
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {'status': 'triggered', 'job_id': job_id}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    uvicorn.run(app, host=GHBOT_HOST, port=GHBOT_PORT, server_header=False)


if __name__ == '__main__':
    main()
