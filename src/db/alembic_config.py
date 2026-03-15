from __future__ import annotations

from collections.abc import Mapping
from configparser import ConfigParser

from alembic.config import Config
from pydantic import ValidationError

from config.settings import Settings


def resolve_database_url(
    config: Config,
    *,
    settings_factory=Settings,
    x_args: Mapping[str, str] | None = None,
) -> str:
    explicit_url = config.attributes.get("database_url")
    if explicit_url:
        return explicit_url

    x_args = x_args or {}
    for key in ("database_url", "db_url", "sqlalchemy_url"):
        if x_args.get(key):
            return x_args[key]

    current_url = config.get_main_option("sqlalchemy.url")
    file_default_url = _get_file_default_database_url(config)
    if current_url and file_default_url and current_url != file_default_url:
        return current_url

    try:
        settings = settings_factory()
    except ValidationError:
        settings = None

    if settings is not None and getattr(settings, "database_url", ""):
        return settings.database_url

    return current_url


def _get_file_default_database_url(config: Config) -> str | None:
    if not config.config_file_name:
        return None

    parser = ConfigParser()
    parser.read(config.config_file_name)
    if parser.has_option(config.config_ini_section, "sqlalchemy.url"):
        return parser.get(config.config_ini_section, "sqlalchemy.url")
    return None
