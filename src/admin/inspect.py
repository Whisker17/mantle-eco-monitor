from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertEvent, MetricSnapshot, SourceRun, WatchlistProtocol


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _serialize_snapshot(snapshot: MetricSnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "entity": snapshot.entity,
        "metric_name": snapshot.metric_name,
        "value": _decimal_to_str(snapshot.value),
        "formatted_value": snapshot.formatted_value,
        "source_platform": snapshot.source_platform,
        "collected_at": snapshot.collected_at.isoformat(),
    }


def _serialize_alert(alert: AlertEvent) -> dict[str, object]:
    return {
        "id": alert.id,
        "entity": alert.entity,
        "metric_name": alert.metric_name,
        "severity": alert.severity,
        "trigger_reason": alert.trigger_reason,
        "detected_at": alert.detected_at.isoformat(),
    }


def _serialize_run(run: SourceRun) -> dict[str, object]:
    return {
        "id": run.id,
        "source_platform": run.source_platform,
        "job_name": run.job_name,
        "status": run.status,
        "records_collected": run.records_collected,
        "started_at": run.started_at.isoformat(),
    }


async def inspect_overview(session: AsyncSession) -> dict[str, object]:
    counts = {
        "metric_snapshots": (await session.execute(select(func.count()).select_from(MetricSnapshot))).scalar() or 0,
        "alert_events": (await session.execute(select(func.count()).select_from(AlertEvent))).scalar() or 0,
        "source_runs": (await session.execute(select(func.count()).select_from(SourceRun))).scalar() or 0,
        "watchlist_protocols": (
            await session.execute(select(func.count()).select_from(WatchlistProtocol))
        ).scalar()
        or 0,
    }

    snapshots = (
        await session.execute(
            select(MetricSnapshot).order_by(MetricSnapshot.collected_at.desc()).limit(5)
        )
    ).scalars().all()
    alerts = (
        await session.execute(
            select(AlertEvent).order_by(AlertEvent.detected_at.desc()).limit(5)
        )
    ).scalars().all()
    runs = (
        await session.execute(
            select(SourceRun).order_by(SourceRun.started_at.desc()).limit(5)
        )
    ).scalars().all()

    return {
        "counts": counts,
        "snapshots": [_serialize_snapshot(snapshot) for snapshot in snapshots],
        "alerts": [_serialize_alert(alert) for alert in alerts],
        "runs": [_serialize_run(run) for run in runs],
    }


async def inspect_snapshots(
    session: AsyncSession,
    *,
    entity: str | None = None,
    metric: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    stmt = select(MetricSnapshot).order_by(MetricSnapshot.collected_at.desc()).limit(limit)
    if entity is not None:
        stmt = stmt.where(MetricSnapshot.entity == entity)
    if metric is not None:
        stmt = stmt.where(MetricSnapshot.metric_name == metric)
    snapshots = (await session.execute(stmt)).scalars().all()
    return {"snapshots": [_serialize_snapshot(snapshot) for snapshot in snapshots]}


async def inspect_alerts(
    session: AsyncSession,
    *,
    entity: str | None = None,
    metric: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    stmt = select(AlertEvent).order_by(AlertEvent.detected_at.desc()).limit(limit)
    if entity is not None:
        stmt = stmt.where(AlertEvent.entity == entity)
    if metric is not None:
        stmt = stmt.where(AlertEvent.metric_name == metric)
    alerts = (await session.execute(stmt)).scalars().all()
    return {"alerts": [_serialize_alert(alert) for alert in alerts]}


async def inspect_runs(
    session: AsyncSession,
    *,
    source: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    stmt = select(SourceRun).order_by(SourceRun.started_at.desc()).limit(limit)
    if source is not None:
        stmt = stmt.where(SourceRun.source_platform == source)
    runs = (await session.execute(stmt)).scalars().all()
    return {"runs": [_serialize_run(run) for run in runs]}
