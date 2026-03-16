from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from src.admin.runtime import serialize_admin_value
from src.db.models import AlertEvent, MetricSnapshot
from src.ingestion.base import BaseCollector, MetricRecord
from src.ingestion.coingecko import CoinGeckoCollector
from src.ingestion.defillama import DefiLlamaCollector
from src.scheduler.jobs import run_job_now
from src.scheduler.runtime import run_collection_job


DATA_QUALITY_HISTORY_TARGETS = [
    {"scope": "core", "entity": "mantle", "metric_name": "daily_active_users"},
    {"scope": "core", "entity": "mantle", "metric_name": "active_addresses"},
    {"scope": "core", "entity": "mantle", "metric_name": "tvl"},
    {"scope": "core", "entity": "mantle", "metric_name": "mnt_volume"},
    {"scope": "ecosystem", "entity": None, "metric_name": None},
]

REBUILD_JOB_ORDER = [
    "core_defillama",
    "core_dune",
    "core_coingecko",
    "watchlist_refresh",
    "eco_aave",
    "eco_protocols",
]


def _automated_source_clause(model):
    return or_(
        model.source_platform.is_(None),
        ~model.source_platform.like("admin_%"),
    )


class _RebuildCollector(BaseCollector):
    def __init__(self, *, source_platform: str, collect_fn):
        self._source_platform = source_platform
        self._collect_fn = collect_fn

    @property
    def source_platform(self) -> str:
        return self._source_platform

    async def collect(self) -> list[MetricRecord]:
        return await self._collect_fn()

    async def health_check(self) -> bool:
        return True


async def _run_rebuild_job(
    job_id: str,
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
):
    if job_id == "core_defillama":
        collector = DefiLlamaCollector()
        return await run_collection_job(
            job_id,
            _RebuildCollector(
                source_platform=collector.source_platform,
                collect_fn=collector.collect_chain_tvl_history,
            ),
            session_factory,
        )
    if job_id == "core_coingecko":
        collector = CoinGeckoCollector(api_key=settings.coingecko_api_key)
        return await run_collection_job(
            job_id,
            _RebuildCollector(
                source_platform=collector.source_platform,
                collect_fn=collector.collect_mnt_volume_history,
            ),
            session_factory,
        )
    return await run_job_now(job_id, settings)


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
            job_results[job_id] = serialize_admin_value(
                await _run_rebuild_job(
                    job_id,
                    settings=settings,
                    session_factory=session_factory,
                )
            )
        result["job_results"] = job_results

    return result
