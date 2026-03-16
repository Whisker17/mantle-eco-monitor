from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from src.db.models import AlertEvent, MetricSnapshot
from src.scheduler.jobs import run_job_now


DATA_QUALITY_HISTORY_TARGETS = [
    {"scope": "core", "entity": "mantle", "metric_name": "daily_active_users"},
    {"scope": "core", "entity": "mantle", "metric_name": "active_addresses"},
    {"scope": "ecosystem", "entity": None, "metric_name": None},
]

REBUILD_JOB_ORDER = [
    "core_dune",
    "watchlist_refresh",
    "eco_aave",
    "eco_protocols",
]


def _automated_source_clause(model):
    return or_(
        model.source_platform.is_(None),
        ~model.source_platform.like("admin_%"),
    )


async def clear_automated_history(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    targets: list[dict[str, str | None]],
) -> dict[str, int]:
    snapshots_deleted = 0
    alerts_deleted = 0

    async with session_factory() as session:
        for target in targets:
            snapshot_stmt = delete(MetricSnapshot).where(
                MetricSnapshot.scope == target["scope"],
                _automated_source_clause(MetricSnapshot),
            )
            alert_stmt = delete(AlertEvent).where(
                AlertEvent.scope == target["scope"],
                _automated_source_clause(AlertEvent),
            )

            entity = target.get("entity")
            metric_name = target.get("metric_name")
            if entity is not None:
                snapshot_stmt = snapshot_stmt.where(MetricSnapshot.entity == entity)
                alert_stmt = alert_stmt.where(AlertEvent.entity == entity)
            if metric_name is not None:
                snapshot_stmt = snapshot_stmt.where(MetricSnapshot.metric_name == metric_name)
                alert_stmt = alert_stmt.where(AlertEvent.metric_name == metric_name)

            snapshots_deleted += (await session.execute(snapshot_stmt)).rowcount or 0
            alerts_deleted += (await session.execute(alert_stmt)).rowcount or 0

        await session.commit()

    return {
        "snapshots_deleted": snapshots_deleted,
        "alerts_deleted": alerts_deleted,
    }


async def rebuild_data_quality_history(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: Settings,
    apply: bool = False,
    run_jobs: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "targets": DATA_QUALITY_HISTORY_TARGETS,
        "apply": apply,
        "run_jobs": run_jobs,
    }

    if not apply:
        return result

    cleared = await clear_automated_history(
        session_factory,
        targets=DATA_QUALITY_HISTORY_TARGETS,
    )
    result.update(cleared)

    if run_jobs:
        job_results: dict[str, Any] = {}
        for job_id in REBUILD_JOB_ORDER:
            job_results[job_id] = await run_job_now(job_id, settings)
        result["job_results"] = job_results

    return result
