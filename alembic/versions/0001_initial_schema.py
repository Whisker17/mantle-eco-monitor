"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("entity", sa.Text, nullable=False),
        sa.Column("metric_name", sa.Text, nullable=False),
        sa.Column("value", sa.Numeric, nullable=False),
        sa.Column("formatted_value", sa.Text, nullable=True),
        sa.Column("unit", sa.Text, nullable=True),
        sa.Column("source_platform", sa.Text, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_snapshots_lookup",
        "metric_snapshots",
        ["entity", "metric_name", sa.text("collected_at DESC")],
    )
    op.create_index(
        "idx_snapshots_scope_time",
        "metric_snapshots",
        ["scope", sa.text("collected_at DESC")],
    )

    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("entity", sa.Text, nullable=False),
        sa.Column("metric_name", sa.Text, nullable=False),
        sa.Column("current_value", sa.Numeric, nullable=False),
        sa.Column("previous_value", sa.Numeric, nullable=True),
        sa.Column("formatted_value", sa.Text, nullable=True),
        sa.Column("time_window", sa.Text, nullable=False),
        sa.Column("change_pct", sa.Numeric, nullable=True),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("trigger_reason", sa.Text, nullable=False),
        sa.Column("source_platform", sa.Text, nullable=True),
        sa.Column("source_ref", sa.Text, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_ath", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_milestone", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("milestone_label", sa.Text, nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column(
            "ai_eligible", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_alerts_feed",
        "alert_events",
        [sa.text("detected_at DESC"), "severity"],
    )
    op.create_index(
        "idx_alerts_entity",
        "alert_events",
        ["entity", "metric_name", sa.text("detected_at DESC")],
    )
    op.create_index(
        "idx_alerts_cooldown",
        "alert_events",
        ["entity", "metric_name", "cooldown_until"],
    )

    op.create_table(
        "watchlist_protocols",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.Text, unique=True, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("monitoring_tier", sa.Text, nullable=False),
        sa.Column(
            "is_pinned", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("metrics", sa.Text, nullable=False),
        sa.Column(
            "active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "source_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_platform", sa.Text, nullable=False),
        sa.Column("job_name", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column(
            "records_collected", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_source_runs_recent",
        "source_runs",
        ["source_platform", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("source_runs")
    op.drop_table("watchlist_protocols")
    op.drop_table("alert_events")
    op.drop_table("metric_snapshots")
