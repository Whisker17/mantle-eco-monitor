from config.settings import Settings


def test_settings_load_dune_query_ids():
    settings = Settings(
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
        dune_api_key="token",
        dune_daily_active_users_query_id=1,
        dune_active_addresses_query_id=2,
        dune_chain_transactions_query_id=3,
        dune_stablecoin_volume_query_id=4,
        dune_dex_volume_query_id=5,
    )

    assert settings.dune_api_key == "token"
    assert settings.dune_dex_volume_query_id == 5


def test_settings_defaults():
    settings = Settings(
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
    )

    assert settings.ai_enrichment_enabled is False
    assert settings.lark_delivery_enabled is False
    assert settings.scheduler_enabled is True
    assert settings.dune_api_key == ""
    assert settings.coingecko_api_key == ""
