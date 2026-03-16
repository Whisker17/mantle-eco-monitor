from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import WatchlistProtocol
from src.db.repositories import insert_alert, insert_snapshots, insert_source_run, upsert_watchlist
from src.ingestion.base import BaseCollector
from src.protocols.base import ProtocolAdapter
from src.protocols.registry import get_adapter
from src.rules.engine import AlertCandidate, RuleEngine
from src.services.dune_sync import DuneSyncService

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    status: str
    records_collected: int
    alerts_created: int = 0
    error_message: str | None = None


class ProtocolAdapterCollector(BaseCollector):
    def __init__(
        self,
        adapters: list[ProtocolAdapter],
        http_client: httpx.AsyncClient | None = None,
    ):
        self._adapters = adapters
        self._http = http_client

    @property
    def source_platform(self) -> str:
        return "defillama"

    async def collect(self) -> list:
        created_http = self._http is None
        http = self._http or httpx.AsyncClient(timeout=30.0)
        try:
            records = []
            for adapter in self._adapters:
                try:
                    records.extend(await adapter.collect(http))
                except Exception:
                    logger.exception("Failed to collect ecosystem metrics for %s", adapter.slug)
            return records
        finally:
            if created_http:
                await http.aclose()

    async def health_check(self) -> bool:
        return True


async def _persist_alerts(session: AsyncSession, candidates: list[AlertCandidate]) -> int:
    now = datetime.now(tz=timezone.utc)
    inserted = []
    for candidate in candidates:
        inserted.append(
            await insert_alert(
            session,
            scope=candidate.scope,
            entity=candidate.entity,
            metric_name=candidate.metric_name,
            current_value=candidate.current_value,
            previous_value=candidate.previous_value,
            formatted_value=candidate.formatted_value,
            time_window=candidate.time_window,
            change_pct=candidate.change_pct,
            severity=candidate.severity,
            trigger_reason=candidate.trigger_reason,
            source_platform=candidate.source_platform,
            source_ref=candidate.source_ref,
            detected_at=now,
            is_ath=candidate.is_ath,
            is_milestone=candidate.is_milestone,
            milestone_label=candidate.milestone_label,
            cooldown_until=candidate.cooldown_until,
            reviewed=False,
            ai_eligible=False,
            created_at=now,
        )
        )
    return inserted


def _latest_snapshots(snapshots):
    latest = {}
    for snapshot in snapshots:
        key = (snapshot.scope, snapshot.entity, snapshot.metric_name)
        if key not in latest or snapshot.collected_at > latest[key].collected_at:
            latest[key] = snapshot
    return list(latest.values())


async def run_collection_job(
    job_name: str,
    collector: BaseCollector,
    session_factory: async_sessionmaker[AsyncSession],
    notification_service=None,
) -> JobResult:
    started_at = datetime.now(tz=timezone.utc)
    start = time.perf_counter()

    try:
        records = await collector.collect()
        alerts = []
        async with session_factory() as session:
            inserted = await insert_snapshots(session, records)
            candidates = await RuleEngine(session).evaluate(_latest_snapshots(inserted))
            alerts = await _persist_alerts(session, candidates)
            alert_count = len(alerts)
            await insert_source_run(
                session,
                source_platform=collector.source_platform,
                job_name=job_name,
                status="success",
                records_collected=len(inserted),
                latency_ms=int((time.perf_counter() - start) * 1000),
                started_at=started_at,
                completed_at=datetime.now(tz=timezone.utc),
                created_at=datetime.now(tz=timezone.utc),
            )
            await session.commit()
        if notification_service is not None and alerts:
            try:
                await notification_service.deliver_alerts(alerts)
            except Exception:
                logger.exception("Notification delivery failed for job %s", job_name)
        return JobResult(status="success", records_collected=len(inserted), alerts_created=alert_count)
    except Exception as exc:
        logger.exception("Collection job %s failed", job_name)
        async with session_factory() as session:
            await insert_source_run(
                session,
                source_platform=collector.source_platform,
                job_name=job_name,
                status="failed",
                records_collected=0,
                error_message=str(exc),
                latency_ms=int((time.perf_counter() - start) * 1000),
                started_at=started_at,
                completed_at=datetime.now(tz=timezone.utc),
                created_at=datetime.now(tz=timezone.utc),
            )
            await session.commit()
        return JobResult(status="failed", records_collected=0, alerts_created=0, error_message=str(exc))


async def run_dune_sync_job(
    job_name: str,
    sync_service: DuneSyncService,
    session_factory: async_sessionmaker[AsyncSession],
    notification_service=None,
) -> JobResult:
    started_at = datetime.now(tz=timezone.utc)
    start = time.perf_counter()

    try:
        result = await sync_service.sync_all()
        alerts = [
            alert
            for metric_result in result.metric_results
            for alert in metric_result.alerts
        ]
        status = "failed" if result.failed_metrics else "success"
        error_message = "; ".join(
            f"{metric}: {error}" for metric, error in sorted(result.failed_metrics.items())
        ) or None

        async with session_factory() as session:
            await insert_source_run(
                session,
                source_platform="dune",
                job_name=job_name,
                status=status,
                records_collected=result.records_written,
                error_message=error_message,
                latency_ms=int((time.perf_counter() - start) * 1000),
                started_at=started_at,
                completed_at=datetime.now(tz=timezone.utc),
                created_at=datetime.now(tz=timezone.utc),
            )
            await session.commit()

        if notification_service is not None and alerts:
            try:
                await notification_service.deliver_alerts(alerts)
            except Exception:
                logger.exception("Notification delivery failed for job %s", job_name)

        return JobResult(
            status=status,
            records_collected=result.records_written,
            alerts_created=result.alerts_created,
            error_message=error_message,
        )
    except Exception as exc:
        logger.exception("Dune sync job %s failed", job_name)
        async with session_factory() as session:
            await insert_source_run(
                session,
                source_platform="dune",
                job_name=job_name,
                status="failed",
                records_collected=0,
                error_message=str(exc),
                latency_ms=int((time.perf_counter() - start) * 1000),
                started_at=started_at,
                completed_at=datetime.now(tz=timezone.utc),
                created_at=datetime.now(tz=timezone.utc),
            )
            await session.commit()
        return JobResult(status="failed", records_collected=0, alerts_created=0, error_message=str(exc))


async def refresh_watchlist(
    session_factory: async_sessionmaker[AsyncSession],
    manager,
) -> int:
    entries = manager.get_seed()

    async with session_factory() as session:
        await upsert_watchlist(session, entries)
        await session.commit()
    return len(entries)


async def get_active_protocol_adapters(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    exclude_special: bool = True,
) -> list[ProtocolAdapter]:
    async with session_factory() as session:
        result = await session.execute(
            select(WatchlistProtocol)
            .where(WatchlistProtocol.active == True)
            .order_by(WatchlistProtocol.is_pinned.desc(), WatchlistProtocol.slug)
        )
        protocols = result.scalars().all()

    adapters: list[ProtocolAdapter] = []
    for protocol in protocols:
        if exclude_special and protocol.monitoring_tier == "special":
            continue
        adapters.append(get_adapter(protocol.slug, protocol.monitoring_tier))
    return adapters


async def run_source_health_job(
    session_factory: async_sessionmaker[AsyncSession],
    collectors: list[BaseCollector],
) -> dict[str, str]:
    results: dict[str, str] = {}
    async with session_factory() as session:
        for collector in collectors:
            started_at = datetime.now(tz=timezone.utc)
            status = "success"
            error_message = None
            try:
                if not await collector.health_check():
                    status = "failed"
                    error_message = "health_check_failed"
            except Exception as exc:
                status = "failed"
                error_message = str(exc)

            await insert_source_run(
                session,
                source_platform=collector.source_platform,
                job_name="source_health",
                status=status,
                records_collected=0,
                error_message=error_message,
                started_at=started_at,
                completed_at=datetime.now(tz=timezone.utc),
                created_at=datetime.now(tz=timezone.utc),
            )
            results[collector.source_platform] = status
        await session.commit()
    return results
