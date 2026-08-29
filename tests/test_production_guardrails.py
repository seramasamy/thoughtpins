"""States nobody chose must not boot, and money must not move unmetered.

Each test here was written against a defect that existed: an unconditional
DEBUG file sink, a Sentry init that shipped request bodies, a JWT secret with
a dev-string fallback, registration that silently bricks under
REQUIRE_EMAIL_VERIFICATION, a lock nobody set, a bot nobody enabled, a
credential endpoint at the default rate tier, a spoofable rate-limit key,
hosted transcription outside the spend cap, and a register endpoint that let
anyone pre-bind a Telegram chat id they do not own.
"""

from __future__ import annotations

import pytest

from thoughtpins.config import Config, config

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def production(monkeypatch):
    """Shape the config like the hosted deployment, explicit about everything."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setenv("SYSTEM_LOCKED", "false")
    monkeypatch.setattr(config, "SYSTEM_LOCKED", False)
    monkeypatch.setattr(Config, "SYSTEM_LOCKED", False)
    monkeypatch.setenv("ENABLE_TELEGRAM_BOT", "false")
    monkeypatch.setattr(config, "ENABLE_TELEGRAM_BOT", False)
    monkeypatch.setattr(Config, "ENABLE_TELEGRAM_BOT", False)

    def set_pair(key, value):
        monkeypatch.setattr(config, key, value)
        monkeypatch.setattr(Config, key, value)

    return set_pair


# ------------------------------------------------------------------- boot


def test_email_verification_without_delivery_cannot_boot(production):
    production("REQUIRE_EMAIL_VERIFICATION", True)
    problems = config.validate_startup()
    assert any("REQUIRE_EMAIL_VERIFICATION" in p for p in problems), problems


def test_email_verification_off_is_not_flagged(production):
    production("REQUIRE_EMAIL_VERIFICATION", False)
    assert not any("REQUIRE_EMAIL_VERIFICATION" in p for p in config.validate_startup())


def test_a_lock_nobody_chose_cannot_boot(production, monkeypatch):
    production("SYSTEM_LOCKED", True)
    monkeypatch.delenv("SYSTEM_LOCKED", raising=False)
    assert any("SYSTEM_LOCKED" in p for p in config.validate_startup())


def test_a_deliberate_lock_still_boots(production, monkeypatch):
    production("SYSTEM_LOCKED", True)
    monkeypatch.setenv("SYSTEM_LOCKED", "true")
    assert not any("locked by its default" in p for p in config.validate_startup())


def test_a_bot_enabled_only_by_token_presence_cannot_boot(production, monkeypatch):
    production("ENABLE_TELEGRAM_BOT", True)
    production("TELEGRAM_ALLOWED_USER_IDS", [12345])
    monkeypatch.delenv("ENABLE_TELEGRAM_BOT", raising=False)
    assert any("only because TELEGRAM_BOT_TOKEN" in p for p in config.validate_startup())


def test_a_bot_enabled_on_purpose_is_not_flagged(production, monkeypatch):
    production("ENABLE_TELEGRAM_BOT", True)
    production("TELEGRAM_ALLOWED_USER_IDS", [12345])
    monkeypatch.setenv("ENABLE_TELEGRAM_BOT", "true")
    assert not any("only because TELEGRAM_BOT_TOKEN" in p for p in config.validate_startup())


def test_jwt_secret_fallback_is_fatal_in_production(production):
    production("JWT_SECRET", "")
    production("API_KEY", "an-api-key-that-must-not-sign-tokens")
    from thoughtpins.auth import _jwt_secret

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _jwt_secret()


def test_jwt_secret_fallback_survives_development(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(Config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "JWT_SECRET", "")
    monkeypatch.setattr(Config, "JWT_SECRET", "")
    from thoughtpins.auth import _jwt_secret

    assert _jwt_secret()


# ------------------------------------------------------------- rate limiting


def test_setting_a_password_is_rate_limited_as_a_credential_operation():
    from thoughtpins.api_gateway import _rate_limit_for_path

    assert _rate_limit_for_path("/v1/account/password") == config.RATE_LIMIT_AUTH_PER_MINUTE


def test_vault_chunk_uploads_sit_in_the_ingest_tier():
    from thoughtpins.api_gateway import _rate_limit_for_path

    chunk_path = "/v1/import/obsidian/uploads/some-transfer/chunks"
    assert _rate_limit_for_path(chunk_path) == config.RATE_LIMIT_INGEST_PER_MINUTE


def test_client_ip_ignores_sender_written_forwarded_entries():
    """The sender controls every X-Forwarded-For entry except the last."""
    from thoughtpins.api_gateway import _client_ip

    class FakeRequest:
        headers = {"X-Forwarded-For": "6.6.6.6, 7.7.7.7, 203.0.113.9"}
        client = None

    assert _client_ip(FakeRequest()) == "203.0.113.9"


# ------------------------------------------------------------------ spending


def test_hosted_transcription_checks_the_budget_before_spending(monkeypatch):
    import thoughtpins.usage as usage
    from thoughtpins.media.transcription import _transcribe_hosted

    monkeypatch.setattr(config, "TRANSCRIPTION_API_KEY", "key")

    def refuse(user_id, **kwargs):
        raise usage.UsageBudgetExceeded("user")

    monkeypatch.setattr(usage, "ensure_budget_available", refuse)
    called = []
    monkeypatch.setattr(
        "httpx.Client.post",
        lambda self, *a, **k: called.append(True),
    )
    with pytest.raises(usage.UsageBudgetExceeded):
        _transcribe_hosted(b"x" * 1000, suffix=".m4a", language=None)
    assert not called, "the provider was called after the budget refused the spend"


def test_hosted_transcription_records_its_spend(monkeypatch):
    import httpx

    import thoughtpins.usage as usage
    from thoughtpins.media.transcription import _transcribe_hosted

    monkeypatch.setattr(config, "TRANSCRIPTION_API_KEY", "key")
    monkeypatch.setattr(usage, "ensure_budget_available", lambda *a, **k: None)
    recorded = {}

    def record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(usage, "record_llm_usage", record)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "hello", "language": "en"}

    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **k: FakeResponse())
    # 1.2 MB at ~500 KB/minute rounds up to 3 minutes.
    result = _transcribe_hosted(b"x" * 1_200_000, suffix=".m4a", language=None)
    assert result.text == "hello"
    assert recorded["operation"] == "transcription"
    assert recorded["cost_usd_override"] == pytest.approx(3 * config.TRANSCRIPTION_COST_PER_MINUTE_USD)


# ---------------------------------------------------------------- register


@pytest.fixture
def client(isolated_db):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app

    return TestClient(app)


def test_register_refuses_a_telegram_chat_id(client):
    response = client.post("/v1/auth/register", json={"telegram_chat_id": "424242"})
    assert response.status_code == 422
    assert "Telegram" in response.json()["error"]["message"]


def test_register_refuses_a_telegram_chat_id_alongside_credentials(client):
    response = client.post(
        "/v1/auth/register",
        json={"email": "squatter@thoughtpins.com", "password": PASSPHRASE, "telegram_chat_id": "424242"},
    )
    assert response.status_code == 422


def test_ordinary_registration_still_works(client):
    response = client.post(
        "/v1/auth/register",
        json={"email": "ordinary@thoughtpins.com", "password": PASSPHRASE},
    )
    assert response.status_code == 200, response.text


# ------------------------------------------------------------------- sentry


def test_the_sentry_scrubber_strips_bodies_and_credentials():
    from thoughtpins.logging_config import _scrub_sentry_event

    event = {
        "request": {
            "data": {"text": "a private journal entry"},
            "cookies": {"session": "abc"},
            "query_string": "q=secret",
            "headers": {"Authorization": "Bearer ey123", "User-Agent": "x", "Cookie": "c=1"},
        },
        "user": {"id": "user-1"},
        "exception": {"values": []},
    }
    scrubbed = _scrub_sentry_event(event, {})
    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert scrubbed["request"]["query_string"] == ""
    assert "Authorization" not in scrubbed["request"]["headers"]
    assert "Cookie" not in scrubbed["request"]["headers"]
    assert "user" not in scrubbed
    assert scrubbed["request"]["headers"]["User-Agent"] == "x"
    assert scrubbed["exception"] == {"values": []}


def test_the_production_file_sink_is_gone(monkeypatch, tmp_path):
    """In production, logging must have exactly one sink: stderr."""
    from loguru import logger

    from thoughtpins.logging_config import setup_logging

    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    monkeypatch.setattr(Config, "SENTRY_DSN", "")
    setup_logging()
    try:
        assert len(logger._core.handlers) == 1
    finally:
        logger.remove()


def test_development_keeps_the_file_sink(monkeypatch):
    from loguru import logger

    from thoughtpins.logging_config import setup_logging

    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(Config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    monkeypatch.setattr(Config, "SENTRY_DSN", "")
    setup_logging()
    try:
        assert len(logger._core.handlers) == 2
    finally:
        logger.remove()
