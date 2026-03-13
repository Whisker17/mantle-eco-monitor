from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.api.schemas import SnapshotListResponse, SnapshotResponse
from src.db.models import MetricSnapshot

metrics_router = APIRouter()


@metrics_router.get("/api/metrics/latest", response_model=SnapshotListResponse)
async def get_latest_metrics(
    scope: str | None = None,
    entity: str | None = None,
    metric_name: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    subq = (
        select(
            MetricSnapshot.entity,
            MetricSnapshot.metric_name,
            func.max(MetricSnapshot.collected_at).label("max_collected"),
        )
        .group_by(MetricSnapshot.entity, MetricSnapshot.metric_name)
    )

    if scope:
        subq = subq.where(MetricSnapshot.scope == scope)
    if entity:
        subq = subq.where(MetricSnapshot.entity == entity)
    if metric_name:
        subq = subq.where(MetricSnapshot.metric_name == metric_name)

    subq = subq.subquery()

    stmt = (
        select(MetricSnapshot)
        .join(
            subq,
            (MetricSnapshot.entity == subq.c.entity)
            & (MetricSnapshot.metric_name == subq.c.metric_name)
            & (MetricSnapshot.collected_at == subq.c.max_collected),
        )
    )
    result = await session.execute(stmt)
    snapshots = result.scalars().all()

    return SnapshotListResponse(
        snapshots=[
            SnapshotResponse(
                entity=s.entity,
                metric_name=s.metric_name,
                value=str(s.value),
                formatted_value=s.formatted_value,
                source_platform=s.source_platform,
                collected_at=s.collected_at,
            )
            for s in snapshots
        ]
    )


@metrics_router.get("/api/metrics/history", response_model=SnapshotListResponse)
async def get_metrics_history(
    entity: str,
    metric_name: str,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_db_session),
):
    if since is None:
        since = datetime.now(tz=timezone.utc) - timedelta(days=30)
    if until is None:
        until = datetime.now(tz=timezone.utc)

    stmt = (
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

    result = await session.execute(stmt)
    snapshots = result.scalars().all()

    return SnapshotListResponse(
        snapshots=[
            SnapshotResponse(
                entity=s.entity,
                metric_name=s.metric_name,
                value=str(s.value),
                formatted_value=s.formatted_value,
                source_platform=s.source_platform,
                collected_at=s.collected_at,
            )
            for s in snapshots
        ]
    )
