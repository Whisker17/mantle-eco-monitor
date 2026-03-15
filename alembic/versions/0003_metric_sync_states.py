"""add metric sync states and daily snapshot key

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.add_column(sa.Column("collected_day", sa.Date(), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE metric_snapshots SET collected_day = timezone('UTC', collected_at)::date"
        )
    else:
        op.execute("UPDATE metric_snapshots SET collected_day = date(collected_at)")

    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.alter_column("collected_day", existing_type=sa.Date(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_metric_snapshots_daily",
            ["scope", "entity", "metric_name", "collected_day"],
        )

    op.create_table(
        "metric_sync_states",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_platform", sa.Text, nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("entity", sa.Text, nullable=False),
        sa.Column("metric_name", sa.Text, nullable=False),
        sa.Column("last_synced_date", sa.Date, nullable=True),
        sa.Column("last_backfilled_date", sa.Date, nullable=True),
        sa.Column(
            "backfill_status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "last_sync_status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint(
            "source_platform",
            "scope",
            "entity",
            "metric_name",
            name="uq_metric_sync_states_key",
        ),
    )
    op.create_index(
        "idx_metric_sync_states_lookup",
        "metric_sync_states",
        ["source_platform", "scope", "entity", "metric_name"],
    )


def downgrade() -> None:
    op.drop_index("idx_metric_sync_states_lookup", table_name="metric_sync_states")
    op.drop_table("metric_sync_states")

    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.drop_constraint("uq_metric_snapshots_daily", type_="unique")
        batch_op.drop_column("collected_day")
