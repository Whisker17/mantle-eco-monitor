from config.settings import Settings


def test_settings_load_public_source_first_dune_query_id():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
        dune_api_key="token",
        dune_stablecoin_volume_query_id=4,
    )

    assert settings.dune_api_key == "token"
    assert settings.dune_stablecoin_volume_query_id == 4
    assert "dune_daily_active_users_query_id" not in settings.model_fields
    assert "dune_active_addresses_query_id" not in settings.model_fields
    assert "dune_chain_transactions_query_id" not in settings.model_fields
    assert "dune_dex_volume_query_id" not in settings.model_fields


def test_settings_ignores_legacy_dune_env_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
                "DUNE_DAILY_ACTIVE_USERS_QUERY_ID=1",
                "DUNE_ACTIVE_ADDRESSES_QUERY_ID=2",
                "DUNE_CHAIN_TRANSACTIONS_QUERY_ID=3",
                "DUNE_DEX_VOLUME_QUERY_ID=5",
                "DUNE_STABLECOIN_VOLUME_QUERY_ID=4",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.database_url == "postgresql+asyncpg://x:y@localhost:5432/mantle_monitor"
    assert settings.dune_stablecoin_volume_query_id == 4


def test_settings_defaults():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
    )

    assert settings.ai_enrichment_enabled is False
    assert settings.lark_delivery_enabled is False
    assert settings.scheduler_enabled is True
    assert settings.scheduler_profile == "prod"
    assert settings.scheduler_config_path == "config/scheduler.toml"
    assert settings.dune_api_key == ""
    assert settings.coingecko_api_key == ""


def test_settings_allow_scheduler_profile_overrides():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
        scheduler_profile="dev_live",
        scheduler_config_path="/tmp/custom-scheduler.toml",
    )

    assert settings.scheduler_profile == "dev_live"
    assert settings.scheduler_config_path == "/tmp/custom-scheduler.toml"
