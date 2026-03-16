from __future__ import annotations

from decimal import Decimal
from typing import Any

from config.settings import Settings
from src.api.deps import get_session_factory
from src.ingestion.coingecko import CoinGeckoCollector
from src.ingestion.defillama import DefiLlamaCollector
from src.ingestion.dune import DuneClient, DuneCollector
from src.ingestion.growthepie import GrowthepieCollector
from src.ingestion.l2beat import L2BeatCollector
from src.scheduler.jobs import JOB_REGISTRY, run_job_now


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _serialize_record(record) -> dict[str, Any]:
    return {
        "scope": record.scope,
        "entity": record.entity,
        "metric_name": record.metric_name,
        "value": _decimal_to_str(record.value),
        "unit": record.unit,
        "source_platform": record.source_platform,
        "source_ref": record.source_ref,
        "collected_at": record.collected_at.isoformat(),
    }


def _build_dry_run_collector(job_id: str, settings: Settings | None = None, session_factory=None):
    if job_id == "core_defillama":
        return DefiLlamaCollector()
    if job_id == "core_growthepie":
        return GrowthepieCollector()
    if job_id == "core_l2beat":
        return L2BeatCollector()
    if job_id == "core_coingecko":
        settings = settings or Settings()
        return CoinGeckoCollector(api_key=settings.coingecko_api_key)
    if job_id == "core_dune":
        settings = settings or Settings()
        return DuneCollector(DuneClient(settings.dune_api_key), settings)
    raise ValueError(f"Dry-run not supported for job: {job_id}")


async def collect_job(
    job_id: str,
    *,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if job_id not in JOB_REGISTRY:
        raise ValueError(f"Unknown scheduler job id: {job_id}")

    if not dry_run:
        settings = settings or Settings()
        result = await run_job_now(job_id, settings)
        return {
            "mode": "run",
            "job_id": job_id,
            "result": result,
        }

    session_factory = get_session_factory(settings) if settings is not None else None
    collector = _build_dry_run_collector(job_id, settings=settings, session_factory=session_factory)
    records = await collector.collect()
    return {
        "mode": "dry_run",
        "job_id": job_id,
        "records_collected": len(records),
        "records": [_serialize_record(record) for record in records],
    }
