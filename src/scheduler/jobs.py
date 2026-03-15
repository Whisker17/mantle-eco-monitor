from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from apscheduler import Scheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import Settings
from src.api.deps import get_session_factory
from src.ingestion.coingecko import CoinGeckoCollector
from src.ingestion.defillama import DefiLlamaCollector
from src.ingestion.dune import DuneClient, DuneCollector
from src.ingestion.growthepie import GrowthepieCollector
from src.ingestion.l2beat import L2BeatCollector
from src.protocols.aave import AaveAdapter
from src.protocols.watchlist import WatchlistManager
from src.scheduler.runtime import (
    ProtocolAdapterCollector,
    get_active_protocol_adapters,
    refresh_watchlist,
    run_collection_job,
    run_source_health_job,
)

logger = logging.getLogger(__name__)


def _get_runtime_dependencies():
    settings = Settings()
    session_factory = get_session_factory(settings)
    return settings, session_factory


async def core_defillama_job():
    logger.info("Running core_defillama collection")
    _, session_factory = _get_runtime_dependencies()
    return await run_collection_job("core_defillama", DefiLlamaCollector(), session_factory)


async def core_growthepie_job():
    logger.info("Running core_growthepie collection")
    _, session_factory = _get_runtime_dependencies()
    return await run_collection_job("core_growthepie", GrowthepieCollector(), session_factory)


async def core_dune_job():
    logger.info("Running core_dune collection")
    settings, session_factory = _get_runtime_dependencies()
    collector = DuneCollector(DuneClient(settings.dune_api_key), settings)
    return await run_collection_job("core_dune", collector, session_factory)


async def core_l2beat_job():
    logger.info("Running core_l2beat collection")
    _, session_factory = _get_runtime_dependencies()
    return await run_collection_job("core_l2beat", L2BeatCollector(), session_factory)


async def core_coingecko_job():
    logger.info("Running core_coingecko collection")
    settings, session_factory = _get_runtime_dependencies()
    return await run_collection_job(
        "core_coingecko",
        CoinGeckoCollector(api_key=settings.coingecko_api_key),
        session_factory,
    )


async def eco_protocols_job():
    logger.info("Running eco_protocols collection")
    _, session_factory = _get_runtime_dependencies()
    adapters = await get_active_protocol_adapters(session_factory)
    if not adapters:
        await refresh_watchlist(session_factory, WatchlistManager())
        adapters = await get_active_protocol_adapters(session_factory)
    return await run_collection_job(
        "eco_protocols",
        ProtocolAdapterCollector(adapters),
        session_factory,
    )


async def eco_aave_job():
    logger.info("Running eco_aave collection")
    _, session_factory = _get_runtime_dependencies()
    return await run_collection_job(
        "eco_aave",
        ProtocolAdapterCollector([AaveAdapter()]),
        session_factory,
    )


async def watchlist_refresh_job():
    logger.info("Running watchlist_refresh")
    _, session_factory = _get_runtime_dependencies()
    count = await refresh_watchlist(session_factory, WatchlistManager())
    return {"status": "refreshed", "count": count}


async def source_health_job():
    logger.info("Running source_health check")
    settings, session_factory = _get_runtime_dependencies()
    collectors = [
        DefiLlamaCollector(),
        GrowthepieCollector(),
        L2BeatCollector(),
        CoinGeckoCollector(api_key=settings.coingecko_api_key),
        DuneCollector(DuneClient(settings.dune_api_key), settings),
    ]
    return await run_source_health_job(session_factory, collectors)


JOB_REGISTRY = {
    "core_defillama": core_defillama_job,
    "core_growthepie": core_growthepie_job,
    "core_dune": core_dune_job,
    "core_l2beat": core_l2beat_job,
    "core_coingecko": core_coingecko_job,
    "eco_protocols": eco_protocols_job,
    "eco_aave": eco_aave_job,
    "watchlist_refresh": watchlist_refresh_job,
    "source_health": source_health_job,
}


def load_scheduler_profile(
    settings: Settings,
    *,
    use_default_profile: bool = False,
) -> tuple[str, dict[str, Any]]:
    config = tomllib.loads(Path(settings.scheduler_config_path).read_text(encoding="utf-8"))
    profiles = config.get("profiles", {})

    profile_name = config.get("active_profile", "prod")
    if not use_default_profile:
        profile_name = settings.scheduler_profile or profile_name

    profile = profiles.get(profile_name)
    if profile is None:
        raise ValueError(f"Unknown scheduler profile: {profile_name}")

    jobs = profile.get("jobs", {})
    for job_id in jobs:
        if job_id not in JOB_REGISTRY:
            raise ValueError(f"Unknown scheduler job id: {job_id}")

    return profile_name, profile


def is_scheduler_enabled(settings: Settings) -> bool:
    if not settings.scheduler_enabled:
        return False

    _, profile = load_scheduler_profile(settings)
    return profile.get("scheduler_enabled", True)


async def run_job_now(job_id: str, settings: Settings | None = None):
    if job_id not in JOB_REGISTRY:
        raise ValueError(f"Unknown scheduler job id: {job_id}")

    settings = settings or Settings()
    _, profile = load_scheduler_profile(settings)
    job_config = profile.get("jobs", {}).get(job_id, {})
    if job_config.get("mode") == "disabled":
        raise ValueError(f"Scheduler job is disabled in profile: {job_id}")

    return await JOB_REGISTRY[job_id]()


def _build_trigger(job_id: str, job_config: dict[str, Any], timezone: str | None):
    mode = job_config.get("mode")
    if mode == "cron":
        return CronTrigger(
            hour=job_config.get("hour"),
            minute=job_config.get("minute"),
            second=job_config.get("second", 0),
            timezone=timezone,
        )
    if mode == "interval":
        return IntervalTrigger(
            weeks=job_config.get("weeks", 0),
            days=job_config.get("days", 0),
            hours=job_config.get("hours", 0),
            minutes=job_config.get("minutes", 0),
            seconds=job_config.get("seconds", 0),
        )
    if mode in {"manual", "disabled"}:
        return None
    raise ValueError(f"Unsupported scheduler mode for {job_id}: {mode}")


def build_scheduler(settings: Settings | None = None) -> Scheduler:
    settings = settings or Settings()
    _, profile = load_scheduler_profile(settings)
    scheduler = Scheduler()
    timezone = profile.get("timezone")
    jobs = profile.get("jobs", {})

    for job_id, job_config in jobs.items():
        trigger = _build_trigger(job_id, job_config, timezone)
        if trigger is None:
            continue

        scheduler.configure_task(job_id, func=JOB_REGISTRY[job_id])
        scheduler.add_schedule(
            job_id,
            trigger=trigger,
            id=job_id,
        )

    return scheduler
