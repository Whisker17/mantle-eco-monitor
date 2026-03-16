from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from src.admin.runtime import serialize_admin_value
from src.ingestion.base import BaseCollector, MetricRecord
from src.ingestion.coingecko import CoinGeckoCollector
from src.ingestion.defillama import DefiLlamaCollector
from src.ingestion.growthepie import GrowthepieCollector
from src.ingestion.l2beat import L2BeatCollector
from src.protocols.aave import AaveAdapter
from src.protocols.aggregate import AggregateAdapter
from src.protocols.dex import DexAdapter
from src.protocols.generic import GenericAdapter
from src.protocols.watchlist import WatchlistManager
from src.scheduler.jobs import run_job_now
from src.scheduler.runtime import (
    ProtocolAdapterCollector,
    get_active_protocol_adapters,
    refresh_watchlist,
    run_collection_job,
    run_dune_sync_job,
)
from src.services.dune_sync import DuneSyncService


INITIAL_HISTORY_JOB_ORDER = [
    "watchlist_refresh",
    "core_defillama_history",
    "core_growthepie_history",
    "core_l2beat_history",
    "core_dune_history",
    "core_coingecko_history",
    "eco_aave_history",
    "eco_protocols_history",
]


class _BootstrapCollector(BaseCollector):
    def __init__(
        self,
        *,
        source_platform: str,
        collect_fn: Callable[[], Awaitable[list[MetricRecord]]],
    ):
        self._source_platform = source_platform
        self._collect_fn = collect_fn

    @property
    def source_platform(self) -> str:
        return self._source_platform

    async def collect(self) -> list[MetricRecord]:
        return await self._collect_fn()

    async def health_check(self) -> bool:
        return True


class _ProtocolHistoryCollector(BaseCollector):
    def __init__(self, adapters):
        self._adapters = adapters

    @property
    def source_platform(self) -> str:
        return "defillama"

    async def collect(self) -> list[MetricRecord]:
        async with httpx.AsyncClient(timeout=30.0) as http:
            records: list[MetricRecord] = []
            for adapter in self._adapters:
                records.extend(await _collect_adapter_history(adapter, http, days=90))
            return records

    async def health_check(self) -> bool:
        return True


async def _collect_adapter_history(adapter, http: httpx.AsyncClient, *, days: int) -> list[MetricRecord]:
    if isinstance(adapter, AaveAdapter):
        return await adapter.collect_history(http, days=days)
    if isinstance(adapter, AggregateAdapter):
        records: list[MetricRecord] = []
        records.extend(await adapter.collect_tvl_history(http, days=days))
        records.extend(await adapter.collect_volume_history(http, days=days))
        return records
    if isinstance(adapter, DexAdapter):
        records: list[MetricRecord] = []
        records.extend(await adapter.collect_tvl_history(http, days=days))
        records.extend(await adapter.collect_volume_history(http, days=days))
        return records
    if isinstance(adapter, GenericAdapter):
        return await adapter.collect_tvl_history(http, days=days)
    raise TypeError(f"Unsupported adapter for history bootstrap: {type(adapter).__name__}")


async def _run_bootstrap_job(
    job_id: str,
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
):
    if job_id == "watchlist_refresh":
        return await run_job_now("watchlist_refresh", settings)

    if job_id == "core_defillama_history":
        collector = DefiLlamaCollector()

        async def collect_records() -> list[MetricRecord]:
            records: list[MetricRecord] = []
            records.extend(await collector.collect_chain_tvl_history())
            records.extend(await collector.collect_stablecoin_supply_history(days=90))
            records.extend(await collector.collect_stablecoin_mcap_history(days=90))
            records.extend(await collector.collect_chain_dex_volume_history(days=90))
            return records

        return await run_collection_job(
            job_id,
            _BootstrapCollector(
                source_platform=collector.source_platform,
                collect_fn=collect_records,
            ),
            session_factory,
        )

    if job_id == "core_growthepie_history":
        collector = GrowthepieCollector()
        return await run_collection_job(
            job_id,
            _BootstrapCollector(
                source_platform=collector.source_platform,
                collect_fn=lambda: collector.collect_recent_history(days=90),
            ),
            session_factory,
        )

    if job_id == "core_l2beat_history":
        collector = L2BeatCollector()
        return await run_collection_job(
            job_id,
            _BootstrapCollector(
                source_platform=collector.source_platform,
                collect_fn=lambda: collector.collect_total_value_secured_history(days=90),
            ),
            session_factory,
        )

    if job_id == "core_dune_history":
        return await run_dune_sync_job(
            job_id,
            DuneSyncService(settings=settings, session_factory=session_factory),
            session_factory,
        )

    if job_id == "core_coingecko_history":
        collector = CoinGeckoCollector(api_key=settings.coingecko_api_key)
        return await run_collection_job(
            job_id,
            _BootstrapCollector(
                source_platform=collector.source_platform,
                collect_fn=lambda: collector.collect_mnt_volume_history(days=90),
            ),
            session_factory,
        )

    if job_id == "eco_aave_history":
        return await run_collection_job(
            job_id,
            _ProtocolHistoryCollector([AaveAdapter()]),
            session_factory,
        )

    if job_id == "eco_protocols_history":
        adapters = await get_active_protocol_adapters(session_factory)
        if not adapters:
            await refresh_watchlist(session_factory, WatchlistManager())
            adapters = await get_active_protocol_adapters(session_factory)
        return await run_collection_job(
            job_id,
            _ProtocolHistoryCollector(adapters),
            session_factory,
        )

    raise ValueError(f"Unknown bootstrap job id: {job_id}")


async def bootstrap_initial_history(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: Settings,
    apply: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "apply": apply,
        "jobs": INITIAL_HISTORY_JOB_ORDER,
    }

    if not apply:
        return result

    job_results: dict[str, Any] = {}
    for job_id in INITIAL_HISTORY_JOB_ORDER:
        job_results[job_id] = serialize_admin_value(
            await _run_bootstrap_job(
                job_id,
                settings=settings,
                session_factory=session_factory,
            )
        )
    result["job_results"] = job_results
    return result
