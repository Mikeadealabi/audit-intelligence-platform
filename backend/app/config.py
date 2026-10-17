from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://audit:audit@localhost:5460/audit_dev"
    jwt_secret: str = "dev-only-insecure-default-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    local_storage_dir: str = "./local_storage"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_rows_per_import: int = 50_000
    vat_rate_percent: float = 7.5

    # No default: the model ID is an explicit, documented choice, not a guess.
    # Verified against the current Anthropic API docs on 2026-10-17 (see
    # docs/claude-tool-contract.md). Unset means "Claude investigation disabled".
    anthropic_api_key: str | None = None
    anthropic_model_id: str | None = None
    llm_request_timeout_seconds: float = 60.0
    llm_max_tool_turns: int = 6
    llm_max_tool_result_records: int = 25
    llm_max_investigations_per_tenant_per_day: int = 50


settings = Settings()
