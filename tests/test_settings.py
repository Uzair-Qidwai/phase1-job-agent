from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.settings import Settings


def test_settings_do_not_require_live_credentials(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.anthropic_api_key is None
    assert settings.postgres_url is None


def test_required_credentials_fail_only_when_used(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    settings = Settings(_env_file=None)

    with pytest.raises(RuntimeError, match="POSTGRES_URL"):
        settings.require_postgres_url()

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        settings.require_anthropic_api_key()


def test_scheduler_time_is_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, PIPELINE_HOUR=25)


def test_invalid_ranking_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RANKING_MODE="silent-auto-promote")


def test_short_api_token_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, API_TOKEN="too-short")


def test_valid_api_token_is_accepted() -> None:
    settings = Settings(
        _env_file=None,
        API_TOKEN="phase2-test-token-with-enough-entropy",
    )
    assert settings.api_token == "phase2-test-token-with-enough-entropy"
