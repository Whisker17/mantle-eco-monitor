from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertEvent, DeliveryEvent, MetricSnapshot, SourceRun, WatchlistProtocol
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
    inserted: list[MetricSnapshot] = []
    formatted_values = formatted_values or {}

    for rec in records:
        existing = await session.execute(
            select(MetricSnapshot).where(
                MetricSnapshot.entity == rec.entity,
                MetricSnapshot.metric_name == rec.metric_name,
                func.date(MetricSnapshot.collected_at) == rec.collected_at.date(),
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

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
            created_at=datetime.now(tz=timezone.utc),
        )
        session.add(snapshot)
        inserted.append(snapshot)

    await session.flush()
    return inserted


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
) -> MetricSnapshot | None:
    now = datetime.now(tz=timezone.utc)

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
        cutoff = _window_cutoff(window, now)
        stmt = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.entity == entity,
                MetricSnapshot.metric_name == metric_name,
                MetricSnapshot.collected_at >= cutoff,
            )
            .order_by(MetricSnapshot.collected_at.asc())
            .limit(1)
        )

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
    from datetime import timedelta

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
