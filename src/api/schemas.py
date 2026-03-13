from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: int
    scope: str
    entity: str
    metric_name: str
    current_value: str
    formatted_value: str | None
    time_window: str
    change_pct: str | None
    severity: str
    trigger_reason: str
    source_platform: str | None
    source_ref: str | None
    detected_at: datetime
    is_ath: bool
    is_milestone: bool
    milestone_label: str | None
    reviewed: bool
    ai_eligible: bool

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    total: int
    alerts: list[AlertResponse]


class ReviewRequest(BaseModel):
    reviewed: bool = True
    review_note: str | None = None


class SnapshotResponse(BaseModel):
    entity: str
    metric_name: str
    value: str
    formatted_value: str | None
    source_platform: str
    collected_at: datetime

    model_config = {"from_attributes": True}


class SnapshotListResponse(BaseModel):
    snapshots: list[SnapshotResponse]


class WatchlistItemResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    category: str
    monitoring_tier: str
    is_pinned: bool
    metrics: list[str] | str
    active: bool

    model_config = {"from_attributes": True}


class WatchlistResponse(BaseModel):
    protocols: list[WatchlistItemResponse]


class HealthResponse(BaseModel):
    status: str
    db: str | None = None
    last_source_runs: dict | None = None
    next_scheduled_run: str | None = None


class SourceRunResponse(BaseModel):
    id: int
    source_platform: str
    job_name: str
    status: str
    records_collected: int
    error_message: str | None
    latency_ms: int | None
    started_at: datetime

    model_config = {"from_attributes": True}


class SourceRunListResponse(BaseModel):
    runs: list[SourceRunResponse]
