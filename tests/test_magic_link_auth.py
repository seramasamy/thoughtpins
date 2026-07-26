from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def magic_link_enabled(monkeypatch):
    from thoughtpins.config import config

    monkeypatch.setattr(config, "MAGIC_LINK_ENABLED", True)
    monkeypatch.setattr(config, "MAGIC_LINK_ALLOW_REGISTRATION", True)
    monkeypatch.setattr(config, "SYSTEM_LOCKED", False)
    monkeypatch.setattr(config, "EMAIL_PROVIDER", "none")
    return config


def _capture_tokens(monkeypatch) -> list[str]:
    """Capture issued tokens; delivery is disabled so we cannot read an inbox."""
    from thoughtpins import magic_link

    issued: list[str] = []
    original = magic_link.issue_magic_link

    def spy(session, email, **kwargs):
        token = original(session, email, **kwargs)
        issued.append(token)
        return token

    monkeypatch.setattr(magic_link, "issue_magic_link", spy)
    monkeypatch.setattr("thoughtpins.api_routes.auth.issue_magic_link", spy)
    return issued


def test_disabled_by_default(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    assert client.post("/v1/auth/magic-link/request", json={"email": "a@example.com"}).status_code == 404


def test_request_and_consume_creates_account_and_signs_in(isolated_db, magic_link_enabled, monkeypatch):
    from thoughtpins.api import app

    issued = _capture_tokens(monkeypatch)
    client = TestClient(app)

    assert client.post("/v1/auth/magic-link/request", json={"email": "New@Example.com "}).status_code == 200
    assert len(issued) == 1

    consumed = client.post("/v1/auth/magic-link/consume", json={"token": issued[0]})
    assert consumed.status_code == 200, consumed.text
    access_token = consumed.json()["access_token"]

    me = client.get("/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


def test_token_is_single_use(isolated_db, magic_link_enabled, monkeypatch):
    from thoughtpins.api import app

    issued = _capture_tokens(monkeypatch)
    client = TestClient(app)
    client.post("/v1/auth/magic-link/request", json={"email": "once@example.com"})

    assert client.post("/v1/auth/magic-link/consume", json={"token": issued[0]}).status_code == 200
    replay = client.post("/v1/auth/magic-link/consume", json={"token": issued[0]})
    assert replay.status_code == 400


def test_expired_token_is_rejected(isolated_db, magic_link_enabled, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from thoughtpins.api import app
    from thoughtpins.db import MagicLinkToken
    from thoughtpins.store import get_session

    issued = _capture_tokens(monkeypatch)
    client = TestClient(app)
    client.post("/v1/auth/magic-link/request", json={"email": "stale@example.com"})

    session = get_session()
    try:
        record = session.query(MagicLinkToken).filter(MagicLinkToken.email == "stale@example.com").first()
        record.expires_at_utc = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    assert client.post("/v1/auth/magic-link/consume", json={"token": issued[0]}).status_code == 400


def test_forged_token_is_rejected(isolated_db, magic_link_enabled):
    from thoughtpins.api import app

    client = TestClient(app)
    assert client.post("/v1/auth/magic-link/consume", json={"token": "tpm_not_a_real_token_value"}).status_code == 400
    assert client.post("/v1/auth/magic-link/consume", json={"token": "wrong_prefix_aaaaaaaaaaaaaaa"}).status_code == 400


def test_send_rate_limit_is_per_email(isolated_db, magic_link_enabled, monkeypatch):
    """Requesting repeatedly must not keep mailing the address."""
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "MAGIC_LINK_REQUESTS_PER_HOUR", 2)
    issued = _capture_tokens(monkeypatch)
    client = TestClient(app)

    for _ in range(5):
        response = client.post("/v1/auth/magic-link/request", json={"email": "flood@example.com"})
        # Always 200 so the endpoint never reveals whether a limit was hit.
        assert response.status_code == 200

    assert len(issued) == 2


def test_response_does_not_reveal_whether_account_exists(isolated_db, magic_link_enabled, monkeypatch):
    from thoughtpins.api import app

    _capture_tokens(monkeypatch)
    client = TestClient(app)
    client.post("/v1/auth/register", json={"email": "known@example.com", "password": "correct horse battery"})

    known = client.post("/v1/auth/magic-link/request", json={"email": "known@example.com"})
    unknown = client.post("/v1/auth/magic-link/request", json={"email": "unknown@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_existing_password_account_can_sign_in_by_link(isolated_db, magic_link_enabled, monkeypatch):
    """The recovery path for a forgotten password."""
    from thoughtpins.api import app

    issued = _capture_tokens(monkeypatch)
    client = TestClient(app)
    client.post("/v1/auth/register", json={"email": "forgot@example.com", "password": "correct horse battery"})

    client.post("/v1/auth/magic-link/request", json={"email": "forgot@example.com"})
    consumed = client.post("/v1/auth/magic-link/consume", json={"token": issued[-1]})

    assert consumed.status_code == 200
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {consumed.json()['access_token']}"})
    assert me.json()["email"] == "forgot@example.com"


def test_registration_blocked_when_system_locked(isolated_db, magic_link_enabled, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    issued = _capture_tokens(monkeypatch)
    client = TestClient(app)
    client.post("/v1/auth/magic-link/request", json={"email": "locked@example.com"})
    assert len(issued) == 1

    monkeypatch.setattr(config, "SYSTEM_LOCKED", True)
    assert client.post("/v1/auth/magic-link/consume", json={"token": issued[0]}).status_code == 403


def test_production_rejects_logging_provider(monkeypatch):
    """A 'none' provider in production would log links instead of sending."""
    # validate_startup is a classmethod reading class attributes, so these must
    # be patched on Config itself rather than on the config instance.
    from thoughtpins.config import Config, config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "MAGIC_LINK_ENABLED", True)
    monkeypatch.setattr(Config, "EMAIL_PROVIDER", "none")

    problems = config.validate_startup()
    assert any("EMAIL_PROVIDER must deliver real mail" in p for p in problems)


def test_production_requires_short_link_lifetime(monkeypatch):
    from thoughtpins.config import Config, config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "MAGIC_LINK_ENABLED", True)
    monkeypatch.setattr(Config, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(Config, "EMAIL_FROM_ADDRESS", "noreply@example.com")
    monkeypatch.setattr(Config, "MAGIC_LINK_TTL_MINUTES", 1440)

    problems = config.validate_startup()
    assert any("MAGIC_LINK_TTL_MINUTES must be 60 or less" in p for p in problems)
