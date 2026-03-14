from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.api.schemas import HealthResponse, SourceRunListResponse, SourceRunResponse
from src.db.models import SourceRun

health_router = APIRouter()


KNOWN_SOURCE_PLATFORMS = ["defillama", "growthepie", "l2beat", "dune", "coingecko"]


def _serialize_next_scheduled_run(scheduler) -> str | None:
    if scheduler is None:
        return None

    schedules = scheduler.get_schedules()
    if not schedules:
        return None

    next_fire_times = [schedule.next_fire_time for schedule in schedules if getattr(schedule, "next_fire_time", None) is not None]
    if not next_fire_times:
        return None

    if isinstance(next_fire_times[0], str):
        return next_fire_times[0]
    return min(next_fire_times).isoformat()


async def _latest_source_runs(session: AsyncSession) -> dict:
    result = await session.execute(
        select(SourceRun).order_by(SourceRun.started_at.desc())
    )
    rows = result.scalars().all()

    latest: dict[str, dict] = {}
    for row in rows:
        if row.source_platform in latest:
            continue
        latest[row.source_platform] = {
            "status": row.status,
            "at": row.started_at.isoformat(),
        }
        if row.error_message:
            latest[row.source_platform]["error"] = row.error_message

    for source_platform in KNOWN_SOURCE_PLATFORMS:
        latest.setdefault(source_platform, {"status": "not_run", "at": None})
    return latest


@health_router.get("/api/health", response_model=HealthResponse)
async def health(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    try:
        await session.execute(text("SELECT 1"))
        last_source_runs = await _latest_source_runs(session)
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "db": "unreachable",
                "last_source_runs": None,
                "next_scheduled_run": _serialize_next_scheduled_run(getattr(request.app.state, "scheduler", None)),
            },
        )

    status = "healthy"
    if any(run["status"] == "failed" for run in last_source_runs.values()):
        status = "degraded"

    return HealthResponse(
        status=status,
        db="connected",
        last_source_runs=last_source_runs,
        next_scheduled_run=_serialize_next_scheduled_run(getattr(request.app.state, "scheduler", None)),
    )


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
