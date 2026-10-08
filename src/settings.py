"""Validated application configuration for Phase 2."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings with explicit validation and safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_input_cost_per_mtok: float = Field(
        default=0.0, ge=0.0, alias="ANTHROPIC_INPUT_COST_PER_MTOK"
    )
    anthropic_output_cost_per_mtok: float = Field(
        default=0.0, ge=0.0, alias="ANTHROPIC_OUTPUT_COST_PER_MTOK"
    )
    postgres_url: str | None = Field(default=None, alias="POSTGRES_URL")

    gmail_client_id: str | None = Field(default=None, alias="GMAIL_CLIENT_ID")
    gmail_client_secret: str | None = Field(default=None, alias="GMAIL_CLIENT_SECRET")
    gmail_refresh_token: str | None = Field(default=None, alias="GMAIL_REFRESH_TOKEN")
    gmail_sender: str | None = Field(default=None, alias="GMAIL_SENDER")
    digest_recipient: str | None = Field(default=None, alias="DIGEST_RECIPIENT")

    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")
    api_token: str | None = Field(
        default=None,
        min_length=24,
        max_length=256,
        alias="API_TOKEN",
    )
    pipeline_timezone: str = Field(default="America/Toronto", alias="PIPELINE_TIMEZONE")
    pipeline_hour: int = Field(default=8, ge=0, le=23, alias="PIPELINE_HOUR")
    pipeline_minute: int = Field(default=0, ge=0, le=59, alias="PIPELINE_MINUTE")
    shortlist_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        alias="SHORTLIST_THRESHOLD",
    )
    ranking_mode: str = Field(
        default="deterministic",
        pattern="^(deterministic|semantic)$",
        alias="RANKING_MODE",
    )
    ranking_model: str = Field(
        default="claude-sonnet-4-5",
        alias="RANKING_MODEL",
    )
    source_zero_alert_runs: int = Field(
        default=3,
        ge=1,
        le=30,
        alias="SOURCE_ZERO_ALERT_RUNS",
    )

    def require_postgres_url(self) -> str:
        if not self.postgres_url:
            raise RuntimeError("POSTGRES_URL is required for database operations")
        return self.postgres_url

    def require_anthropic_api_key(self) -> str:
        if not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for live CV generation")
        return self.anthropic_api_key

    def require_gmail_credentials(self) -> tuple[str, str, str, str, str]:
        values = {
            "GMAIL_CLIENT_ID": self.gmail_client_id,
            "GMAIL_CLIENT_SECRET": self.gmail_client_secret,
            "GMAIL_REFRESH_TOKEN": self.gmail_refresh_token,
            "GMAIL_SENDER": self.gmail_sender,
            "DIGEST_RECIPIENT": self.digest_recipient,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing Gmail configuration: " + ", ".join(sorted(missing))
            )
        return (
            self.gmail_client_id,
            self.gmail_client_secret,
            self.gmail_refresh_token,
            self.gmail_sender,
            self.digest_recipient,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
