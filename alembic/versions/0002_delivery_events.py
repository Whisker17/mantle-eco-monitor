"""delivery events

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=True),
        sa.Column("logical_key", sa.Text, nullable=False),
        sa.Column("environment", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "idx_delivery_events_logical_key",
        "delivery_events",
        ["logical_key"],
        unique=True,
    )
    op.create_index(
        "idx_delivery_events_status",
        "delivery_events",
        ["channel", "status"],
    )


def downgrade() -> None:
    op.drop_table("delivery_events")
