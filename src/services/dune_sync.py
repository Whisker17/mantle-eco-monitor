from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from src.db.models import AlertEvent, MetricSnapshot
from src.db.repositories import get_metric_sync_state, insert_alert, upsert_metric_sync_state, upsert_snapshots
from src.ingestion.dune import DUNE_METRIC_SPECS, DuneClient, DuneCollector, DuneMetricSpec
from src.rules.engine import AlertCandidate, RuleEngine


@dataclass
class DuneMetricSyncResult:
    metric_name: str
    fetch_start: date | None
    fetch_end: date | None
    advanced_to: date | None
    backlog_days: int
    records_written: int
    alerts_created: int
    is_bootstrap: bool
    alerts: list[AlertEvent] = field(default_factory=list)


@dataclass
class DuneSyncResult:
    metrics_processed: int
    records_written: int
    alerts_created: int
    metric_results: list[DuneMetricSyncResult] = field(default_factory=list)
    failed_metrics: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _SyncWindow:
    fetch_start: date
    fetch_end: date
    backlog_days: int
    is_bootstrap: bool


def _latest_snapshots(snapshots: Iterable[MetricSnapshot]) -> list[MetricSnapshot]:
    latest: dict[tuple[str, str, str], MetricSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.scope, snapshot.entity, snapshot.metric_name)
        if key not in latest or snapshot.collected_at > latest[key].collected_at:
            latest[key] = snapshot
    return list(latest.values())


async def _persist_alerts(
    session: AsyncSession,
    candidates: list[AlertCandidate],
) -> list[AlertEvent]:
    now = datetime.now(tz=timezone.utc)
    inserted: list[AlertEvent] = []
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


class DuneSyncService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        client: DuneClient | None = None,
        metric_specs: tuple[DuneMetricSpec, ...] = DUNE_METRIC_SPECS,
    ):
        self._settings = settings
        self._session_factory = session_factory
        self._client = client or DuneClient(settings.dune_api_key)
        self._collector = DuneCollector(self._client, settings)
        self._metric_specs = {spec.metric_name: spec for spec in metric_specs}

    async def sync_all(self, *, today: date | None = None) -> DuneSyncResult:
        metric_results: list[DuneMetricSyncResult] = []
        failed_metrics: dict[str, str] = {}

        for spec in self._metric_specs.values():
            if not getattr(self._settings, spec.settings_attr, 0):
                continue
            try:
                metric_results.append(await self.sync_metric(spec.metric_name, today=today))
            except Exception as exc:
                failed_metrics[spec.metric_name] = str(exc)

        return DuneSyncResult(
            metrics_processed=len(metric_results) + len(failed_metrics),
            records_written=sum(result.records_written for result in metric_results),
            alerts_created=sum(result.alerts_created for result in metric_results),
            metric_results=metric_results,
            failed_metrics=failed_metrics,
        )

    async def sync_metric(
        self,
        metric_name: str,
        *,
        today: date | None = None,
    ) -> DuneMetricSyncResult:
        spec = self._metric_specs[metric_name]
        query_id = getattr(self._settings, spec.settings_attr, 0)
        if not query_id:
            return DuneMetricSyncResult(
                metric_name=metric_name,
                fetch_start=None,
                fetch_end=None,
                advanced_to=None,
                backlog_days=0,
                records_written=0,
                alerts_created=0,
                is_bootstrap=False,
            )

        latest_completed_day = self._latest_completed_day(today)

        async with self._session_factory() as session:
            state = await get_metric_sync_state(
                session,
                source_platform="dune",
                scope=spec.scope,
                entity=spec.entity,
                metric_name=spec.metric_name,
            )
            window = self._build_sync_window(spec, state.last_synced_date if state else None, latest_completed_day)
            if window is None:
                return DuneMetricSyncResult(
                    metric_name=metric_name,
                    fetch_start=None,
                    fetch_end=None,
                    advanced_to=state.last_synced_date if state else None,
                    backlog_days=0,
                    records_written=0,
                    alerts_created=0,
                    is_bootstrap=state is None or state.last_synced_date is None,
                )

            records_written = 0
            latest_day_snapshots: list[MetricSnapshot] = []

            try:
                for chunk_start, chunk_end in self._iter_chunks(window.fetch_start, window.fetch_end):
                    rows = await self._client.get_query_result(
                        query_id,
                        params={
                            "start_date": chunk_start.isoformat(),
                            "end_date": chunk_end.isoformat(),
                        },
                    )
                    records = self._collector._map_rows(metric_name=metric_name, rows=rows)
                    snapshots = await upsert_snapshots(session, records)
                    records_written += len(snapshots)
                    if chunk_end == window.fetch_end:
                        latest_day_snapshots = [
                            snapshot for snapshot in snapshots if snapshot.collected_day == latest_completed_day
                        ]
                    await upsert_metric_sync_state(
                        session,
                        source_platform="dune",
                        scope=spec.scope,
                        entity=spec.entity,
                        metric_name=spec.metric_name,
                        last_synced_date=chunk_end,
                        last_backfilled_date=chunk_end if window.is_bootstrap else None,
                        backfill_status="completed" if window.is_bootstrap else None,
                        last_sync_status="success",
                        last_error=None,
                    )
                    await session.commit()
            except Exception as exc:
                await self._mark_metric_failed(spec, error=str(exc), is_bootstrap=window.is_bootstrap)
                raise

            alerts: list[AlertEvent] = []
            if self._should_evaluate_alerts(window) and latest_day_snapshots:
                candidates = await RuleEngine(session).evaluate(_latest_snapshots(latest_day_snapshots))
                alerts = await _persist_alerts(session, candidates)
                await session.commit()

            return DuneMetricSyncResult(
                metric_name=metric_name,
                fetch_start=window.fetch_start,
                fetch_end=window.fetch_end,
                advanced_to=window.fetch_end,
                backlog_days=window.backlog_days,
                records_written=records_written,
                alerts_created=len(alerts),
                is_bootstrap=window.is_bootstrap,
                alerts=alerts,
            )

    def _latest_completed_day(self, today: date | None) -> date:
        anchor = today or datetime.now(tz=timezone.utc).date()
        return anchor - timedelta(days=1)

    def _build_sync_window(
        self,
        spec: DuneMetricSpec,
        last_synced_date: date | None,
        latest_completed_day: date,
    ) -> _SyncWindow | None:
        if latest_completed_day < spec.bootstrap_start:
            return None

        if last_synced_date is None:
            return _SyncWindow(
                fetch_start=spec.bootstrap_start,
                fetch_end=latest_completed_day,
                backlog_days=(latest_completed_day - spec.bootstrap_start).days,
                is_bootstrap=True,
            )

        correction_days = max(getattr(self._settings, "dune_sync_correction_lookback_days", 2), 0)
        correction_offset = max(correction_days - 1, 0)
        fetch_start = max(spec.bootstrap_start, last_synced_date - timedelta(days=correction_offset))
        return _SyncWindow(
            fetch_start=fetch_start,
            fetch_end=latest_completed_day,
            backlog_days=max((latest_completed_day - last_synced_date).days, 0),
            is_bootstrap=False,
        )

    def _iter_chunks(self, start: date, end: date):
        chunk_days = max(getattr(self._settings, "dune_sync_chunk_days", 31), 1)
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=chunk_days - 1), end)
            yield current, chunk_end
            current = chunk_end + timedelta(days=1)

    def _should_evaluate_alerts(self, window: _SyncWindow) -> bool:
        return not window.is_bootstrap and window.backlog_days == 1

    async def _mark_metric_failed(
        self,
        spec: DuneMetricSpec,
        *,
        error: str,
        is_bootstrap: bool,
    ) -> None:
        async with self._session_factory() as session:
            await upsert_metric_sync_state(
                session,
                source_platform="dune",
                scope=spec.scope,
                entity=spec.entity,
                metric_name=spec.metric_name,
                backfill_status="failed" if is_bootstrap else None,
                last_sync_status="failed",
                last_error=error,
            )
            await session.commit()
