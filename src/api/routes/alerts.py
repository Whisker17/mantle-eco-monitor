from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.api.schemas import AlertListResponse, AlertResponse, ReviewRequest
from src.db.models import AlertEvent

alerts_router = APIRouter()


@alerts_router.get("/api/alerts", response_model=AlertListResponse)
async def list_alerts(
    scope: str | None = None,
    entity: str | None = None,
    severity: str | None = None,
    is_ath: bool | None = None,
    is_milestone: bool | None = None,
    reviewed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
):
    if since is None:
        since = datetime.now(tz=timezone.utc) - timedelta(days=7)
    if until is None:
        until = datetime.now(tz=timezone.utc)

    stmt = select(AlertEvent).where(
        AlertEvent.detected_at >= since,
        AlertEvent.detected_at <= until,
    )

    if scope:
        stmt = stmt.where(AlertEvent.scope == scope)
    if entity:
        stmt = stmt.where(AlertEvent.entity == entity)
    if severity:
        stmt = stmt.where(AlertEvent.severity == severity)
    if is_ath is not None:
        stmt = stmt.where(AlertEvent.is_ath == is_ath)
    if is_milestone is not None:
        stmt = stmt.where(AlertEvent.is_milestone == is_milestone)
    if reviewed is not None:
        stmt = stmt.where(AlertEvent.reviewed == reviewed)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AlertEvent.detected_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    alerts = result.scalars().all()

    return AlertListResponse(
        total=total,
        alerts=[
            AlertResponse(
                id=a.id,
                scope=a.scope,
                entity=a.entity,
                metric_name=a.metric_name,
                current_value=str(a.current_value),
                formatted_value=a.formatted_value,
                time_window=a.time_window,
                change_pct=str(a.change_pct) if a.change_pct is not None else None,
                severity=a.severity,
                trigger_reason=a.trigger_reason,
                source_platform=a.source_platform,
                source_ref=a.source_ref,
                detected_at=a.detected_at,
                is_ath=a.is_ath,
                is_milestone=a.is_milestone,
                milestone_label=a.milestone_label,
                reviewed=a.reviewed,
                ai_eligible=a.ai_eligible,
            )
            for a in alerts
        ],
    )


@alerts_router.patch("/api/alerts/{alert_id}/review")
async def review_alert(
    alert_id: int,
    body: ReviewRequest,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(
        select(AlertEvent).where(AlertEvent.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.reviewed = body.reviewed
    if body.review_note is not None:
        alert.review_note = body.review_note
    await session.commit()
    return {"status": "updated", "id": alert_id}
