"""Public ecosystem security dashboard API."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.deps import get_db
from api.models.job import Job, JobStatus


router = APIRouter(prefix='/dashboard', tags=['dashboard'])
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]


class DashboardStats(BaseModel):
    total_scanned: int
    total_findings: int
    high_severity: int
    scanned_last_24h: int


class TrendingContract(BaseModel):
    address: str
    chain: str
    job_id: str
    high_findings: int
    created_at: str


class VulnPattern(BaseModel):
    title: str
    count: int
    percentage: float


class DashboardData(BaseModel):
    stats: DashboardStats
    trending: list[TrendingContract]
    patterns: list[VulnPattern]


@router.get('/{chain}', response_model=DashboardData)
async def get_dashboard(
    chain: str,
    session: DbSessionDep,
) -> DashboardData:
    # All permalink jobs for this chain
    prefix = f'permalink:{chain}:'
    stmt = select(Job).where(
        Job.file_name.startswith(prefix),
        Job.status == JobStatus.succeeded,
        Job.public == True,  # noqa: E712
    )
    jobs = list((await session.scalars(stmt)).all())

    total_findings = 0
    high_severity = 0
    trending = []

    for job in jobs:
        vulns = (job.result or {}).get('vulnerabilities', [])
        highs = sum(1 for v in vulns if v.get('severity') == 'high')
        total_findings += len(vulns)
        high_severity += highs
        address = job.file_name.removeprefix(prefix)
        trending.append(TrendingContract(
            address=address,
            chain=chain,
            job_id=str(job.id),
            high_findings=highs,
            created_at=job.created_at.isoformat() if job.created_at else '',
        ))

    # 24h count
    since = datetime.now(UTC) - timedelta(hours=24)
    recent_count = await session.scalar(
        select(func.count()).select_from(Job).where(
            Job.file_name.startswith(prefix),
            Job.created_at >= since,
        )
    ) or 0

    trending.sort(key=lambda x: (x.high_findings, x.created_at), reverse=True)

    # Vulnerability pattern frequency analysis
    patterns: list[VulnPattern] = []
    if jobs:
        title_counter: Counter[str] = Counter()
        for job in jobs:
            vulns = (job.result or {}).get('vulnerabilities', [])
            for v in vulns:
                raw = v.get('title', '')
                if raw:
                    title_counter[raw.strip().rstrip('.').lower()] += 1
        patterns = [
            VulnPattern(
                title=title,
                count=count,
                percentage=(count / len(jobs)) * 100,
            )
            for title, count in title_counter.most_common(10)
        ]

    return DashboardData(
        stats=DashboardStats(
            total_scanned=len(jobs),
            total_findings=total_findings,
            high_severity=high_severity,
            scanned_last_24h=int(recent_count),
        ),
        trending=trending[:20],
        patterns=patterns,
    )
