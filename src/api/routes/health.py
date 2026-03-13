from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.api.schemas import HealthResponse, SourceRunListResponse, SourceRunResponse
from src.db.models import SourceRun

health_router = APIRouter()


@health_router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@health_router.get("/api/health/sources", response_model=SourceRunListResponse)
async def source_health(
    source_platform: str | None = None,
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = select(SourceRun).order_by(SourceRun.started_at.desc()).limit(limit)
    if source_platform:
        stmt = stmt.where(SourceRun.source_platform == source_platform)

    result = await session.execute(stmt)
    runs = result.scalars().all()

    return SourceRunListResponse(
        runs=[
            SourceRunResponse(
                id=r.id,
                source_platform=r.source_platform,
                job_name=r.job_name,
                status=r.status,
                records_collected=r.records_collected,
                error_message=r.error_message,
                latency_ms=r.latency_ms,
                started_at=r.started_at,
            )
            for r in runs
        ]
    )
