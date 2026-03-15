from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertEvent, MetricSnapshot


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None

    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _serialize_snapshot(snapshot: MetricSnapshot) -> dict[str, str | None]:
    return {
        "scope": snapshot.scope,
        "entity": snapshot.entity,
        "metric_name": snapshot.metric_name,
        "value": _decimal_to_str(snapshot.value),
        "formatted_value": snapshot.formatted_value,
        "source_platform": snapshot.source_platform,
        "source_ref": snapshot.source_ref,
        "collected_at": snapshot.collected_at.isoformat(),
    }


def _serialize_alert(alert: AlertEvent) -> dict[str, str | bool | None]:
    return {
        "scope": alert.scope,
        "entity": alert.entity,
        "metric_name": alert.metric_name,
        "current_value": str(alert.current_value),
        "formatted_value": alert.formatted_value,
        "time_window": alert.time_window,
        "change_pct": _decimal_to_str(alert.change_pct),
        "severity": alert.severity,
        "trigger_reason": alert.trigger_reason,
        "source_platform": alert.source_platform,
        "source_ref": alert.source_ref,
        "detected_at": alert.detected_at.isoformat(),
        "is_ath": alert.is_ath,
        "is_milestone": alert.is_milestone,
        "milestone_label": alert.milestone_label,
    }


async def get_latest_metric(
    session: AsyncSession,
    *,
    entity: str,
    metric_name: str,
    scope: str | None = None,
) -> dict[str, str | None] | None:
    stmt = (
        select(MetricSnapshot)
        .where(
            MetricSnapshot.entity == entity,
            MetricSnapshot.metric_name == metric_name,
        )
        .order_by(MetricSnapshot.collected_at.desc())
        .limit(1)
    )
    if scope is not None:
        stmt = stmt.where(MetricSnapshot.scope == scope)

    result = await session.execute(stmt)
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        return None
    return _serialize_snapshot(snapshot)


async def get_metric_history(
    session: AsyncSession,
    *,
    entity: str,
    metric_name: str,
    since: datetime,
    until: datetime,
    limit: int = 30,
) -> dict[str, object]:
    result = await session.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.entity == entity,
            MetricSnapshot.metric_name == metric_name,
            MetricSnapshot.collected_at >= since,
            MetricSnapshot.collected_at <= until,
        )
        .order_by(MetricSnapshot.collected_at.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()
    return {
        "entity": entity,
        "metric_name": metric_name,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "points": [_serialize_snapshot(snapshot) for snapshot in snapshots],
    }


async def get_recent_alerts(
    session: AsyncSession,
    *,
    limit: int = 10,
    scope: str | None = None,
    entity: str | None = None,
) -> dict[str, object]:
    stmt = select(AlertEvent).order_by(AlertEvent.detected_at.desc()).limit(limit)
    if scope is not None:
        stmt = stmt.where(AlertEvent.scope == scope)
    if entity is not None:
        stmt = stmt.where(AlertEvent.entity == entity)

    result = await session.execute(stmt)
    alerts = result.scalars().all()
    return {"alerts": [_serialize_alert(alert) for alert in alerts]}


async def get_daily_summary_context(
    session: AsyncSession,
    *,
    day: date,
) -> dict[str, object]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)

    snapshot_result = await session.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.collected_at >= start,
            MetricSnapshot.collected_at < end,
        )
        .order_by(MetricSnapshot.collected_at.desc())
    )
    snapshots = snapshot_result.scalars().all()

    latest_snapshots: dict[tuple[str, str, str], MetricSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.scope, snapshot.entity, snapshot.metric_name)
        if key not in latest_snapshots:
            latest_snapshots[key] = snapshot

    alert_result = await session.execute(
        select(AlertEvent)
        .where(
            AlertEvent.detected_at >= start,
            AlertEvent.detected_at < end,
        )
        .order_by(AlertEvent.detected_at.desc())
    )
    alerts = alert_result.scalars().all()

    return {
        "day": day.isoformat(),
        "metrics": [_serialize_snapshot(snapshot) for snapshot in latest_snapshots.values()],
        "alerts": [_serialize_alert(alert) for alert in alerts],
    }
