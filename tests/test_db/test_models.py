from src.db.models import (
    AlertEvent,
    DeliveryEvent,
    MetricSnapshot,
    MetricSyncState,
    SourceRun,
    WatchlistProtocol,
)


def test_expected_tables_exist():
    assert MetricSnapshot.__tablename__ == "metric_snapshots"
    assert MetricSyncState.__tablename__ == "metric_sync_states"
    assert AlertEvent.__tablename__ == "alert_events"
    assert DeliveryEvent.__tablename__ == "delivery_events"
    assert WatchlistProtocol.__tablename__ == "watchlist_protocols"
    assert SourceRun.__tablename__ == "source_runs"


def test_metric_snapshot_has_required_columns():
    cols = {c.name for c in MetricSnapshot.__table__.columns}
    assert cols >= {
        "id", "scope", "entity", "metric_name", "value",
        "formatted_value", "unit", "source_platform", "source_ref",
        "collected_at", "collected_day", "created_at",
    }


def test_metric_sync_state_has_required_columns():
    cols = {c.name for c in MetricSyncState.__table__.columns}
    assert cols >= {
        "id",
        "source_platform",
        "scope",
        "entity",
        "metric_name",
        "last_synced_date",
        "last_backfilled_date",
        "backfill_status",
        "last_sync_status",
        "last_error",
        "created_at",
        "updated_at",
    }


def test_alert_event_has_required_columns():
    cols = {c.name for c in AlertEvent.__table__.columns}
    assert cols >= {
        "id", "scope", "entity", "metric_name", "current_value",
        "previous_value", "formatted_value", "time_window", "change_pct",
        "severity", "trigger_reason", "source_platform", "source_ref",
        "detected_at", "is_ath", "is_milestone", "milestone_label",
        "cooldown_until", "reviewed", "review_note", "ai_eligible",
        "created_at",
    }


def test_watchlist_protocol_has_required_columns():
    cols = {c.name for c in WatchlistProtocol.__table__.columns}
    assert cols >= {
        "id", "slug", "display_name", "category", "monitoring_tier",
        "is_pinned", "metrics", "active", "added_at", "updated_at",
    }


def test_source_run_has_required_columns():
    cols = {c.name for c in SourceRun.__table__.columns}
    assert cols >= {
        "id", "source_platform", "job_name", "status",
        "records_collected", "error_message", "http_status",
        "latency_ms", "started_at", "completed_at", "created_at",
    }


def test_delivery_event_has_required_columns():
    cols = {c.name for c in DeliveryEvent.__table__.columns}
    assert cols >= {
        "id",
        "channel",
        "entity_type",
        "entity_id",
        "logical_key",
        "environment",
        "status",
        "attempt_count",
        "last_error",
        "delivered_at",
        "created_at",
        "updated_at",
    }
