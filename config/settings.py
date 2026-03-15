from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    dune_api_key: str = ""
    coingecko_api_key: str = ""
    dune_stablecoin_volume_query_id: int = 0
    ai_enrichment_enabled: bool = False
    lark_delivery_enabled: bool = False
    lark_bot_enabled: bool = False
    bot_external_actions_enabled: bool = False
    lark_app_id: str = ""
    lark_app_secret: str = ""
    lark_base_url: str = "https://open.larksuite.com"
    lark_verification_token: str = ""
    lark_encrypt_key: str = ""
    lark_environment: str = "dev"
    lark_alert_chat_id_dev: str = ""
    lark_alert_chat_id_prod: str = ""
    lark_summary_chat_id_dev: str = ""
    lark_summary_chat_id_prod: str = ""
    llm_api_base: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    llm_app_name: str = "mantle-eco-monitor"
    llm_app_url: str = "https://github.com/Whisker17/mantle-eco-monitor"
    llm_timeout_seconds: int = 30
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
