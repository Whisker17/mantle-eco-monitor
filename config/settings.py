from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    dune_api_key: str = ""
    coingecko_api_key: str = ""
    dune_stablecoin_volume_query_id: int = 0
    ai_enrichment_enabled: bool = False
    lark_delivery_enabled: bool = False
    scheduler_enabled: bool = True
    scheduler_profile: str = "prod"
    scheduler_config_path: str = "config/scheduler.toml"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
