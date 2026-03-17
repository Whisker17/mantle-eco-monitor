"""move token-level stablecoin transfer breakdown rows to stablecoin scope

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-17
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


TOKEN_LEVEL_SCOPE_WHERE = """
scope = 'core'
and entity like 'mantle:%'
and metric_name in ('stablecoin_transfer_volume', 'stablecoin_transfer_tx_count')
"""


def upgrade() -> None:
    op.execute(
        f"""
        delete from metric_snapshots as src
        where {TOKEN_LEVEL_SCOPE_WHERE}
          and exists (
            select 1
            from metric_snapshots as dst
            where dst.scope = 'stablecoin'
              and dst.entity = src.entity
              and dst.metric_name = src.metric_name
              and dst.collected_day = src.collected_day
          )
        """
    )
    op.execute(
        f"""
        update metric_snapshots
        set scope = 'stablecoin'
        where {TOKEN_LEVEL_SCOPE_WHERE}
        """
    )


def downgrade() -> None:
    op.execute(
        """
        update metric_snapshots
        set scope = 'core'
        where scope = 'stablecoin'
          and entity like 'mantle:%'
          and metric_name in ('stablecoin_transfer_volume', 'stablecoin_transfer_tx_count')
        """
    )
