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
    assert settings.lark_bot_enabled is False
    assert settings.scheduler_enabled is True
    assert settings.scheduler_profile == "prod"
    assert settings.scheduler_config_path == "config/scheduler.toml"
    assert settings.lark_app_id == ""
    assert settings.lark_app_secret == ""
    assert settings.lark_verification_token == ""
    assert settings.lark_encrypt_key == ""
    assert settings.lark_environment == "dev"
    assert settings.lark_alert_chat_id_dev == ""
    assert settings.lark_alert_chat_id_prod == ""
    assert settings.lark_summary_chat_id_dev == ""
    assert settings.lark_summary_chat_id_prod == ""
    assert settings.llm_api_base == ""
    assert settings.llm_api_key == ""
    assert settings.llm_model == ""
    assert settings.llm_timeout_seconds == 30
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


def test_settings_allow_lark_and_llm_overrides():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
        lark_bot_enabled=True,
        lark_app_id="cli_x",
        lark_app_secret="secret_x",
        lark_verification_token="verify_x",
        lark_encrypt_key="encrypt_x",
        lark_environment="prod",
        lark_alert_chat_id_dev="chat_dev_alert",
        lark_alert_chat_id_prod="chat_prod_alert",
        lark_summary_chat_id_dev="chat_dev_summary",
        lark_summary_chat_id_prod="chat_prod_summary",
        llm_api_base="https://llm.example.com/v1",
        llm_api_key="key_x",
        llm_model="gpt-x",
        llm_timeout_seconds=45,
    )

    assert settings.lark_bot_enabled is True
    assert settings.lark_app_id == "cli_x"
    assert settings.lark_app_secret == "secret_x"
    assert settings.lark_verification_token == "verify_x"
    assert settings.lark_encrypt_key == "encrypt_x"
    assert settings.lark_environment == "prod"
    assert settings.lark_alert_chat_id_dev == "chat_dev_alert"
    assert settings.lark_alert_chat_id_prod == "chat_prod_alert"
    assert settings.lark_summary_chat_id_dev == "chat_dev_summary"
    assert settings.lark_summary_chat_id_prod == "chat_prod_summary"
    assert settings.llm_api_base == "https://llm.example.com/v1"
    assert settings.llm_api_key == "key_x"
    assert settings.llm_model == "gpt-x"
    assert settings.llm_timeout_seconds == 45
