from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://audit:audit@localhost:5460/audit_dev"
    jwt_secret: str = "dev-only-insecure-default-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    # Used only to build invite links (there is no email-sending infra — an admin
    # copies and sends the link themselves). No code default assumption beyond
    # local dev; set to the real public frontend URL in any other environment.
    frontend_base_url: str = "http://localhost:3090"
    invite_expires_hours: int = 168  # 7 days
    local_storage_dir: str = "./local_storage"
    # Dev-only insecure default, same convention as jwt_secret — must be a real
    # Fernet key (generate with Fernet.generate_key()) and must be changed before
    # any real client data touches this app. Rotating it makes all previously
    # written ciphertext (files + raw_row) permanently unreadable — there is no
    # key-versioning in this slice.
    file_encryption_key: str = "VcetRONpqI6CKNxcvtP23IPpSIU9GSk5hvNmNxrBQnk="
    # Only set true once this app is confirmed to be running behind a real
    # TLS-terminating reverse proxy. Must stay false in local dev (plain HTTP) —
    # see docs/deployment-runbook.md's TLS stance section.
    enable_hsts: bool = False
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
