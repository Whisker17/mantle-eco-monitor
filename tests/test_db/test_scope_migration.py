from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _build_config(db_path: Path) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    return cfg


def test_stablecoin_scope_migration_moves_only_token_level_breakdown_rows(tmp_path):
    db_path = tmp_path / "scope_migration.db"
    cfg = _build_config(db_path)

    command.upgrade(cfg, "0003")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into metric_snapshots (
                        id, scope, entity, metric_name, value, formatted_value, unit,
                        source_platform, source_ref, collected_at, collected_day, created_at
                    ) values
                    (1, 'core', 'mantle:USDT', 'stablecoin_transfer_volume', 120.5, null, 'usd', 'dune', null, '2026-03-14 00:00:00+00:00', '2026-03-14', '2026-03-14 00:00:00+00:00'),
                    (2, 'core', 'mantle:USDT', 'stablecoin_transfer_tx_count', 7, null, 'count', 'dune', null, '2026-03-14 00:00:00+00:00', '2026-03-14', '2026-03-14 00:00:00+00:00'),
                    (3, 'core', 'mantle', 'stablecoin_transfer_volume', 150.5, null, 'usd', 'dune', null, '2026-03-14 00:00:00+00:00', '2026-03-14', '2026-03-14 00:00:00+00:00'),
                    (4, 'core', 'mantle', 'stablecoin_supply', 500000000, null, 'usd', 'defillama', null, '2026-03-14 00:00:00+00:00', '2026-03-14', '2026-03-14 00:00:00+00:00')
                    """
                )
            )

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    select scope, entity, metric_name
                    from metric_snapshots
                    order by entity, metric_name
                    """
                )
            ).fetchall()
    finally:
        engine.dispose()

    assert ("stablecoin", "mantle:USDT", "stablecoin_transfer_tx_count") in rows
    assert ("stablecoin", "mantle:USDT", "stablecoin_transfer_volume") in rows
    assert ("core", "mantle", "stablecoin_transfer_volume") in rows
    assert ("core", "mantle", "stablecoin_supply") in rows
