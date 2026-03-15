from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertEvent, MetricSnapshot, SourceRun, WatchlistProtocol

KNOWN_SOURCE_PLATFORMS = ["defillama", "growthepie", "l2beat", "dune", "coingecko"]


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


def _serialize_source_run(run: SourceRun) -> dict[str, object]:
    return {
        "id": run.id,
        "source_platform": run.source_platform,
        "job_name": run.job_name,
        "status": run.status,
        "records_collected": run.records_collected,
        "error_message": run.error_message,
        "latency_ms": run.latency_ms,
        "started_at": run.started_at.isoformat(),
    }


def _serialize_watchlist(protocol: WatchlistProtocol) -> dict[str, object]:
    return {
        "id": protocol.id,
        "slug": protocol.slug,
        "display_name": protocol.display_name,
        "category": protocol.category,
        "monitoring_tier": protocol.monitoring_tier,
        "is_pinned": protocol.is_pinned,
        "metrics": protocol.metrics,
        "active": protocol.active,
    }


def _serialize_next_scheduled_run(scheduler) -> str | None:
    if scheduler is None:
        return None

    schedules = scheduler.get_schedules()
    if not schedules:
        return None

    next_fire_times = [
        schedule.next_fire_time
        for schedule in schedules
        if getattr(schedule, "next_fire_time", None) is not None
    ]
    if not next_fire_times:
        return None

    if isinstance(next_fire_times[0], str):
        return next_fire_times[0]
    return min(next_fire_times).isoformat()


async def _latest_source_runs(session: AsyncSession) -> dict[str, dict[str, object | None]]:
    result = await session.execute(
        select(SourceRun).order_by(SourceRun.started_at.desc())
    )
    rows = result.scalars().all()

    latest: dict[str, dict[str, object | None]] = {}
    for row in rows:
        if row.source_platform in latest:
            continue
        latest[row.source_platform] = {
            "status": row.status,
            "at": row.started_at.isoformat(),
        }
        if row.error_message:
            latest[row.source_platform]["error"] = row.error_message

    for source_platform in KNOWN_SOURCE_PLATFORMS:
        latest.setdefault(source_platform, {"status": "not_run", "at": None})
    return latest


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


async def get_alerts_list(
    session: AsyncSession,
    *,
    scope: str | None = None,
    entity: str | None = None,
    severity: str | None = None,
    is_ath: bool | None = None,
    is_milestone: bool | None = None,
    reviewed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    if since is None:
        since = datetime.now(tz=UTC) - timedelta(days=7)
    if until is None:
        until = datetime.now(tz=UTC)

    stmt = select(AlertEvent).where(
        AlertEvent.detected_at >= since,
        AlertEvent.detected_at <= until,
    )
    if scope is not None:
        stmt = stmt.where(AlertEvent.scope == scope)
    if entity is not None:
        stmt = stmt.where(AlertEvent.entity == entity)
    if severity is not None:
        stmt = stmt.where(AlertEvent.severity == severity)
    if is_ath is not None:
        stmt = stmt.where(AlertEvent.is_ath == is_ath)
    if is_milestone is not None:
        stmt = stmt.where(AlertEvent.is_milestone == is_milestone)
    if reviewed is not None:
        stmt = stmt.where(AlertEvent.reviewed == reviewed)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    result = await session.execute(
        stmt.order_by(AlertEvent.detected_at.desc()).offset(offset).limit(limit)
    )
    alerts = result.scalars().all()
    return {
        "total": total,
        "alerts": [_serialize_alert(alert) for alert in alerts],
    }


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
    result = await get_alerts_list(
        session,
        limit=limit,
        scope=scope,
        entity=entity,
    )
    return {"alerts": result["alerts"]}


async def get_health_status(
    session: AsyncSession,
    *,
    scheduler=None,
) -> dict[str, object]:
    last_source_runs = await _latest_source_runs(session)
    status = "healthy"
    if any(run["status"] == "failed" for run in last_source_runs.values()):
        status = "degraded"

    return {
        "status": status,
        "db": "connected",
        "last_source_runs": last_source_runs,
        "next_scheduled_run": _serialize_next_scheduled_run(scheduler),
    }


async def get_source_health(
    session: AsyncSession,
    *,
    source_platform: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    stmt = select(SourceRun).order_by(SourceRun.started_at.desc()).limit(limit)
    if source_platform is not None:
        stmt = stmt.where(SourceRun.source_platform == source_platform)

    result = await session.execute(stmt)
    runs = result.scalars().all()
    return {"runs": [_serialize_source_run(run) for run in runs]}


async def get_watchlist(session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(WatchlistProtocol)
        .where(WatchlistProtocol.active == True)
        .order_by(WatchlistProtocol.is_pinned.desc(), WatchlistProtocol.slug)
    )
    protocols = result.scalars().all()
    return {"protocols": [_serialize_watchlist(protocol) for protocol in protocols]}


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
