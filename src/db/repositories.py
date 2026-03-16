from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AlertEvent,
    DeliveryEvent,
    MetricSnapshot,
    MetricSyncState,
    SourceRun,
    WatchlistProtocol,
)
from src.ingestion.base import MetricRecord


class TimeWindow(str, Enum):
    D7 = "7d"
    MTD = "mtd"
    M1 = "1m"
    M3 = "3m"
    M6 = "6m"
    YTD = "ytd"
    Y1 = "1y"
    ALL_TIME = "all_time"
    ATH = "ath"


def _normalize_watchlist_metrics(metrics: list[str] | str | None) -> list[str]:
    if metrics is None:
        return ["tvl"]

    if isinstance(metrics, str):
        try:
            decoded = json.loads(metrics)
        except json.JSONDecodeError:
            return [metrics]
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
        return [str(decoded)]

    return [str(item) for item in metrics]


async def insert_snapshots(
    session: AsyncSession,
    records: list[MetricRecord],
    formatted_values: dict[str, str] | None = None,
) -> list[MetricSnapshot]:
    return await upsert_snapshots(session, records, formatted_values)


async def upsert_snapshots(
    session: AsyncSession,
    records: list[MetricRecord],
    formatted_values: dict[str, str] | None = None,
) -> list[MetricSnapshot]:
    inserted: list[MetricSnapshot] = []
    formatted_values = formatted_values or {}

    for rec in records:
        collected_day = rec.collected_at.date()
        existing = await session.execute(
            select(MetricSnapshot).where(
                MetricSnapshot.scope == rec.scope,
                MetricSnapshot.entity == rec.entity,
                MetricSnapshot.metric_name == rec.metric_name,
                MetricSnapshot.collected_day == collected_day,
            )
        )
        snapshot = existing.scalar_one_or_none()
        if snapshot is None:
            snapshot = MetricSnapshot(
                scope=rec.scope,
                entity=rec.entity,
                metric_name=rec.metric_name,
                value=rec.value,
                formatted_value=formatted_values.get(rec.metric_name),
                unit=rec.unit,
                source_platform=rec.source_platform,
                source_ref=rec.source_ref,
                collected_at=rec.collected_at,
                collected_day=collected_day,
                created_at=datetime.now(tz=timezone.utc),
            )
            session.add(snapshot)
            inserted.append(snapshot)
        else:
            formatted_value = formatted_values.get(rec.metric_name)
            if (
                snapshot.value == rec.value
                and snapshot.formatted_value == formatted_value
                and snapshot.unit == rec.unit
                and snapshot.source_platform == rec.source_platform
                and snapshot.source_ref == rec.source_ref
                and snapshot.collected_day == collected_day
            ):
                continue

            snapshot.value = rec.value
            snapshot.formatted_value = formatted_value
            snapshot.unit = rec.unit
            snapshot.source_platform = rec.source_platform
            snapshot.source_ref = rec.source_ref
            snapshot.collected_at = rec.collected_at
            snapshot.collected_day = collected_day
            inserted.append(snapshot)

    await session.flush()
    return inserted


async def get_metric_sync_state(
    session: AsyncSession,
    *,
    source_platform: str,
    scope: str,
    entity: str,
    metric_name: str,
) -> MetricSyncState | None:
    result = await session.execute(
        select(MetricSyncState).where(
            MetricSyncState.source_platform == source_platform,
            MetricSyncState.scope == scope,
            MetricSyncState.entity == entity,
            MetricSyncState.metric_name == metric_name,
        )
    )
    return result.scalar_one_or_none()


async def upsert_metric_sync_state(
    session: AsyncSession,
    *,
    source_platform: str,
    scope: str,
    entity: str,
    metric_name: str,
    last_synced_date: date | None = None,
    last_backfilled_date: date | None = None,
    backfill_status: str | None = None,
    last_sync_status: str | None = None,
    last_error: str | None = None,
) -> MetricSyncState:
    state = await get_metric_sync_state(
        session,
        source_platform=source_platform,
        scope=scope,
        entity=entity,
        metric_name=metric_name,
    )
    now = datetime.now(tz=timezone.utc)

    if state is None:
        state = MetricSyncState(
            source_platform=source_platform,
            scope=scope,
            entity=entity,
            metric_name=metric_name,
            last_synced_date=last_synced_date,
            last_backfilled_date=last_backfilled_date,
            backfill_status=backfill_status or "pending",
            last_sync_status=last_sync_status or "pending",
            last_error=last_error,
            created_at=now,
            updated_at=now,
        )
        session.add(state)
    else:
        if last_synced_date is not None:
            state.last_synced_date = last_synced_date
        if last_backfilled_date is not None:
            state.last_backfilled_date = last_backfilled_date
        if backfill_status is not None:
            state.backfill_status = backfill_status
        if last_sync_status is not None:
            state.last_sync_status = last_sync_status
        state.last_error = last_error
        state.updated_at = now

    await session.flush()
    return state


async def insert_alert(session: AsyncSession, **kwargs) -> AlertEvent:
    alert = AlertEvent(**kwargs)
    session.add(alert)
    await session.flush()
    return alert


async def insert_source_run(session: AsyncSession, **kwargs) -> SourceRun:
    run = SourceRun(**kwargs)
    session.add(run)
    await session.flush()
    return run


async def create_delivery_event(session: AsyncSession, **kwargs) -> DeliveryEvent:
    event = DeliveryEvent(**kwargs)
    session.add(event)
    await session.flush()
    return event


async def get_delivery_event_by_logical_key(
    session: AsyncSession,
    logical_key: str,
) -> DeliveryEvent | None:
    result = await session.execute(
        select(DeliveryEvent).where(DeliveryEvent.logical_key == logical_key)
    )
    return result.scalar_one_or_none()


async def mark_delivery_event_delivered(
    session: AsyncSession,
    event: DeliveryEvent,
    *,
    delivered_at: datetime,
) -> DeliveryEvent:
    event.status = "delivered"
    event.attempt_count += 1
    event.last_error = None
    event.delivered_at = delivered_at
    event.updated_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return event


async def mark_delivery_event_failed(
    session: AsyncSession,
    event: DeliveryEvent,
    *,
    error: str,
) -> DeliveryEvent:
    event.status = "failed"
    event.attempt_count += 1
    event.last_error = error
    event.updated_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return event


async def upsert_watchlist(
    session: AsyncSession, entries: list[dict]
) -> list[WatchlistProtocol]:
    result: list[WatchlistProtocol] = []
    for entry in entries:
        metrics_val = _normalize_watchlist_metrics(entry.get("metrics"))
        existing = await session.execute(
            select(WatchlistProtocol).where(WatchlistProtocol.slug == entry["slug"])
        )
        proto = existing.scalar_one_or_none()
        if proto is None:
            proto = WatchlistProtocol(
                slug=entry["slug"],
                display_name=entry.get("display_name", entry["slug"]),
                category=entry.get("category", "other"),
                monitoring_tier=entry.get("tier", "generic"),
                is_pinned=entry.get("pinned", False),
                metrics=metrics_val,
                active=True,
                added_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
            )
            session.add(proto)
        else:
            proto.display_name = entry.get("display_name", proto.display_name)
            proto.category = entry.get("category", proto.category)
            proto.monitoring_tier = entry.get("tier", proto.monitoring_tier)
            proto.is_pinned = entry.get("pinned", proto.is_pinned)
            proto.metrics = metrics_val
            proto.active = True
            proto.updated_at = datetime.now(tz=timezone.utc)
        result.append(proto)

    await session.flush()
    return result


async def get_comparison_snapshot(
    session: AsyncSession,
    entity: str,
    metric_name: str,
    window: TimeWindow,
    *,
    anchor_at: datetime | None = None,
) -> MetricSnapshot | None:
    now = anchor_at or datetime.now(tz=timezone.utc)

    if window == TimeWindow.ATH:
        stmt = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.entity == entity,
                MetricSnapshot.metric_name == metric_name,
            )
            .order_by(MetricSnapshot.value.desc())
            .limit(1)
        )
    elif window == TimeWindow.ALL_TIME:
        stmt = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.entity == entity,
                MetricSnapshot.metric_name == metric_name,
            )
            .order_by(MetricSnapshot.collected_at.asc())
            .limit(1)
        )
    else:
        anchor_day = now.date()
        start_day = _window_start_day(window, anchor_day)
        stmt = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.entity == entity,
                MetricSnapshot.metric_name == metric_name,
                MetricSnapshot.collected_day >= start_day,
                MetricSnapshot.collected_day <= anchor_day,
            )
            .order_by(MetricSnapshot.collected_day.asc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if not _window_has_coverage(window, rows, anchor_day):
            return None
        return rows[0]

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_previous_snapshot(
    session: AsyncSession,
    entity: str,
    metric_name: str,
) -> MetricSnapshot | None:
    stmt = (
        select(MetricSnapshot)
        .where(
            MetricSnapshot.entity == entity,
            MetricSnapshot.metric_name == metric_name,
        )
        .order_by(MetricSnapshot.collected_at.desc())
        .offset(1)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _window_cutoff(window: TimeWindow, now: datetime) -> datetime:
    match window:
        case TimeWindow.D7:
            return now - timedelta(days=7)
        case TimeWindow.MTD:
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        case TimeWindow.M1:
            return now - timedelta(days=30)
        case TimeWindow.M3:
            return now - timedelta(days=90)
        case TimeWindow.M6:
            return now - timedelta(days=180)
        case TimeWindow.YTD:
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        case TimeWindow.Y1:
            return now - timedelta(days=365)
        case _:
            return now - timedelta(days=7)


def _window_start_day(window: TimeWindow, anchor_day: date) -> date:
    match window:
        case TimeWindow.D7:
            return anchor_day - timedelta(days=7)
        case TimeWindow.MTD:
            return anchor_day.replace(day=1)
        case TimeWindow.M1:
            return anchor_day - timedelta(days=30)
        case TimeWindow.M3:
            return anchor_day - timedelta(days=90)
        case TimeWindow.M6:
            return anchor_day - timedelta(days=180)
        case TimeWindow.YTD:
            return anchor_day.replace(month=1, day=1)
        case TimeWindow.Y1:
            return anchor_day - timedelta(days=365)
        case _:
            return anchor_day - timedelta(days=7)


def _window_has_coverage(
    window: TimeWindow,
    rows: list[MetricSnapshot],
    anchor_day: date,
) -> bool:
    if not rows:
        return False

    available_days = {row.collected_day for row in rows}

    if window == TimeWindow.D7:
        start_day = anchor_day - timedelta(days=7)
        if rows[0].collected_day > start_day:
            return False
        present_days = sum(
            1 for offset in range(8) if start_day + timedelta(days=offset) in available_days
        )
        return present_days >= 6

    if window == TimeWindow.MTD:
        month_start = anchor_day.replace(day=1)
        if rows[0].collected_day > month_start + timedelta(days=1):
            return False
        total_days = (anchor_day - month_start).days + 1
        return len(available_days) * 100 >= total_days * 80

    return True
