"""Validated application configuration for Phase 2."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


AgentRole = Literal["researcher", "analyst", "writer", "reviewer"]
Provider = Literal["anthropic", "openai", "gemini"]


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Provider
    model: str = Field(min_length=1)
    input_cost_per_mtok: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_cost_per_mtok: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_output_tokens: int | None = Field(default=None, ge=128, le=16384)


class Settings(BaseSettings):
    """Environment-backed settings with explicit validation and safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY", repr=False)
    anthropic_input_cost_per_mtok: float = Field(
        default=0.0, ge=0.0, alias="ANTHROPIC_INPUT_COST_PER_MTOK"
    )
    anthropic_output_cost_per_mtok: float = Field(
        default=0.0, ge=0.0, alias="ANTHROPIC_OUTPUT_COST_PER_MTOK"
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY", repr=False)
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY", repr=False)
    model_provider: Provider = Field(default="anthropic", alias="MODEL_PROVIDER")
    model_name: str | None = Field(default=None, min_length=1, alias="MODEL_NAME")
    model_input_cost_per_mtok: float | None = Field(default=None, ge=0, allow_inf_nan=False, alias="MODEL_INPUT_COST_PER_MTOK")
    model_output_cost_per_mtok: float | None = Field(default=None, ge=0, allow_inf_nan=False, alias="MODEL_OUTPUT_COST_PER_MTOK")
    agent_models: dict[AgentRole, AgentModelConfig] = Field(default_factory=dict, alias="AGENT_MODELS")
    agent_workflow_enabled: bool = Field(default=False, alias="AGENT_WORKFLOW_ENABLED")
    agent_max_turns: int = Field(default=6, ge=1, le=8, alias="AGENT_MAX_TURNS")
    agent_max_model_calls: int = Field(default=12, ge=1, le=32, alias="AGENT_MAX_MODEL_CALLS")
    agent_timeout_seconds: float = Field(default=90, gt=0, le=300, alias="AGENT_TIMEOUT_SECONDS")
    agent_max_revisions: int = Field(default=1, ge=0, le=2, alias="AGENT_MAX_REVISIONS")

    pipeline_max_model_calls: int = Field(default=100, ge=1, le=1000, alias="PIPELINE_MAX_MODEL_CALLS")
    model_spend_stop_usd: float | None = Field(default=None, gt=0, allow_inf_nan=False, alias="MODEL_SPEND_STOP_USD")
    agent_max_input_bytes: int = Field(default=200000, ge=1000, le=2000000, alias="AGENT_MAX_INPUT_BYTES")
    agent_transient_retries: int = Field(default=1, ge=0, le=2, alias="AGENT_TRANSIENT_RETRIES")
    agent_retry_backoff_seconds: float = Field(default=1, ge=0, le=10, alias="AGENT_RETRY_BACKOFF_SECONDS")

    postgres_url: str | None = Field(default=None, repr=False, alias="POSTGRES_URL")

    gmail_client_id: str | None = Field(default=None, repr=False, alias="GMAIL_CLIENT_ID")
    gmail_client_secret: str | None = Field(default=None, repr=False, alias="GMAIL_CLIENT_SECRET")
    gmail_refresh_token: str | None = Field(default=None, repr=False, alias="GMAIL_REFRESH_TOKEN")
    gmail_sender: str | None = Field(default=None, alias="GMAIL_SENDER")
    digest_recipient: str | None = Field(default=None, alias="DIGEST_RECIPIENT")

    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")
    api_token: str | None = Field(
        default=None,
        min_length=24,
        max_length=256,
        alias="API_TOKEN",
        repr=False,
    )
    api_require_read_auth: bool = Field(default=False, alias="API_REQUIRE_READ_AUTH")
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

    def agent_config(self, role: AgentRole, *, model: str | None = None,
                     max_tokens: int = 4096) -> AgentModelConfig:
        if role in self.agent_models:
            config = self.agent_models[role]
            if model and model != config.model:
                raise ValueError("Model override conflicts with configured specialist")
            return config.model_copy(update={"max_output_tokens": config.max_output_tokens or max_tokens})
        selected = model or self.model_name
        if not selected and self.model_provider == "anthropic":
            selected = self.ranking_model  # Preserve the existing baseline explicitly.
        if not selected:
            raise ValueError("MODEL_NAME or a per-role AGENT_MODELS entry is required")
        input_rate, output_rate = self.model_input_cost_per_mtok, self.model_output_cost_per_mtok
        configured_name = self.model_name or (self.ranking_model if self.model_provider == "anthropic" else None)
        if model and model != configured_name:
            input_rate = output_rate = None  # Never reuse another model's configured price.
        if self.model_provider == "anthropic" and selected == self.ranking_model:
            if input_rate is None and self.anthropic_input_cost_per_mtok > 0:
                input_rate = self.anthropic_input_cost_per_mtok
            if output_rate is None and self.anthropic_output_cost_per_mtok > 0:
                output_rate = self.anthropic_output_cost_per_mtok
        return AgentModelConfig(provider=self.model_provider, model=selected,
                                input_cost_per_mtok=input_rate, output_cost_per_mtok=output_rate,
                                max_output_tokens=max_tokens)

    def require_model_key(self, provider: Provider) -> str:
        key = {"anthropic": self.anthropic_api_key, "openai": self.openai_api_key,
               "gemini": self.gemini_api_key}[provider]
        if not key:
            raise RuntimeError(f"{provider.upper()}_API_KEY is required for this provider")
        return key

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
