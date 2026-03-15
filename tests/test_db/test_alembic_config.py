from pathlib import Path

from alembic.config import Config

from src.db.alembic_config import resolve_database_url


def _build_config() -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    return Config(str(repo_root / "alembic.ini"))


def test_resolve_database_url_prefers_explicit_config_attribute():
    cfg = _build_config()
    cfg.attributes["database_url"] = "postgresql+asyncpg://explicit:pass@localhost:5432/explicit_db"

    url = resolve_database_url(
        cfg,
        settings_factory=lambda: type("Settings", (), {"database_url": "postgresql+asyncpg://env:pass@localhost:5432/env_db"})(),
        x_args={"db_url": "postgresql+asyncpg://cli:pass@localhost:5432/cli_db"},
    )

    assert url == "postgresql+asyncpg://explicit:pass@localhost:5432/explicit_db"


def test_resolve_database_url_prefers_cli_x_arg_over_env_and_ini():
    cfg = _build_config()

    url = resolve_database_url(
        cfg,
        settings_factory=lambda: type("Settings", (), {"database_url": "postgresql+asyncpg://env:pass@localhost:5432/env_db"})(),
        x_args={"db_url": "postgresql+asyncpg://cli:pass@localhost:5432/cli_db"},
    )

    assert url == "postgresql+asyncpg://cli:pass@localhost:5432/cli_db"


def test_resolve_database_url_prefers_programmatic_main_option_override():
    cfg = _build_config()
    cfg.set_main_option("sqlalchemy.url", "sqlite+aiosqlite:////tmp/override.db")

    url = resolve_database_url(
        cfg,
        settings_factory=lambda: type("Settings", (), {"database_url": "postgresql+asyncpg://env:pass@localhost:5432/env_db"})(),
        x_args={},
    )

    assert url == "sqlite+aiosqlite:////tmp/override.db"


def test_resolve_database_url_prefers_env_over_ini_default():
    cfg = _build_config()

    url = resolve_database_url(
        cfg,
        settings_factory=lambda: type("Settings", (), {"database_url": "postgresql+asyncpg://env:pass@localhost:5432/env_db"})(),
        x_args={},
    )

    assert url == "postgresql+asyncpg://env:pass@localhost:5432/env_db"


def test_resolve_database_url_falls_back_to_alembic_ini_default():
    cfg = _build_config()

    url = resolve_database_url(
        cfg,
        settings_factory=lambda: type("Settings", (), {"database_url": ""})(),
        x_args={},
    )

    assert url == "postgresql+asyncpg://monitor:password@localhost:5432/mantle_monitor"
