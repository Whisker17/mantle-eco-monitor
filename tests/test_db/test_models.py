from src.db.models import AlertEvent, MetricSnapshot, SourceRun, WatchlistProtocol


def test_expected_tables_exist():
    assert MetricSnapshot.__tablename__ == "metric_snapshots"
    assert AlertEvent.__tablename__ == "alert_events"
    assert WatchlistProtocol.__tablename__ == "watchlist_protocols"
    assert SourceRun.__tablename__ == "source_runs"


def test_metric_snapshot_has_required_columns():
    cols = {c.name for c in MetricSnapshot.__table__.columns}
    assert cols >= {
        "id", "scope", "entity", "metric_name", "value",
        "formatted_value", "unit", "source_platform", "source_ref",
        "collected_at", "created_at",
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
