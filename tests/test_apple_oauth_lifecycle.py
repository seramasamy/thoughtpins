from __future__ import annotations

from datetime import datetime, timezone

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient


def _apple_signing_key() -> tuple[str, object]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return private_pem, private_key.public_key()


def _configure_apple(monkeypatch, *, private_key: str, client_id: str = "com.thoughtpins.test") -> None:
    from thoughtpins.config import config

    values = {
        "APPLE_OAUTH_CLIENT_IDS": [client_id],
        "APPLE_OAUTH_TEAM_ID": "TESTTEAM01",
        "APPLE_OAUTH_KEY_ID": "TESTKEY001",
        "APPLE_OAUTH_PRIVATE_KEY": private_key,
        "APPLE_OAUTH_PRIVATE_KEY_PATH": "",
        "APPLE_OAUTH_REDIRECT_URIS": ["https://app.example.com/app/"],
        "APPLE_OAUTH_TIMEOUT_SECONDS": 10,
        "ALLOW_OAUTH_REGISTRATION": True,
    }
    for name, value in values.items():
        monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(type(config), name, value)


def test_web_configuration_selects_services_id_even_when_native_audience_is_first(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "APPLE_OAUTH_CLIENT_IDS", ["com.thoughtpins.app", "com.thoughtpins.web.test"])
    monkeypatch.setattr(config, "APPLE_OAUTH_WEB_CLIENT_ID", "com.thoughtpins.web.test")
    response = TestClient(app).get("/v1/client-config")
    assert response.status_code == 200
    assert response.json()["oauth_apple_client_id"] == "com.thoughtpins.web.test"


def test_native_only_configuration_does_not_advertise_bundle_id_to_web(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "APPLE_OAUTH_CLIENT_IDS", ["com.thoughtpins.app"])
    monkeypatch.setattr(config, "APPLE_OAUTH_WEB_CLIENT_ID", "")
    body = TestClient(app).get("/v1/client-config").json()
    assert body["oauth_apple_enabled"] is True
    assert body["oauth_apple_client_id"] is None


def test_apple_client_secret_is_short_lived_and_scoped(monkeypatch):
    from thoughtpins.apple_oauth import APPLE_AUDIENCE, create_apple_client_secret

    private_pem, public_key = _apple_signing_key()
    _configure_apple(monkeypatch, private_key=private_pem)
    issued_at = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    encoded = create_apple_client_secret("com.thoughtpins.test", now=issued_at)
    payload = jwt.decode(
        encoded,
        public_key,
        algorithms=["ES256"],
        audience=APPLE_AUDIENCE,
        options={"verify_exp": False, "verify_iat": False},
    )

    assert payload["iss"] == "TESTTEAM01"
    assert payload["sub"] == "com.thoughtpins.test"
    assert payload["exp"] - payload["iat"] == 300
    assert jwt.get_unverified_header(encoded)["kid"] == "TESTKEY001"


def test_apple_exchange_and_revocation_send_expected_form_without_leaking_errors(monkeypatch):
    from thoughtpins.apple_oauth import (
        APPLE_REVOKE_URL,
        APPLE_TOKEN_URL,
        AppleOAuthError,
        exchange_apple_authorization_code,
        revoke_apple_refresh_token,
    )

    private_pem, _ = _apple_signing_key()
    _configure_apple(monkeypatch, private_key=private_pem)
    calls: list[tuple[str, dict[str, str]]] = []

    def post_ok(url, *, data, headers, timeout):
        assert headers == {"Accept": "application/json"}
        assert timeout == 10
        calls.append((url, data))
        body = (
            {"refresh_token": "apple-refresh-secret", "id_token": "apple-code-id-token"}
            if url == APPLE_TOKEN_URL
            else {}
        )
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    grant = exchange_apple_authorization_code(
        "one-time-code",
        client_id="com.thoughtpins.test",
        redirect_uri="https://app.example.com/app/",
        post_form=post_ok,
    )
    revoke_apple_refresh_token(
        grant.refresh_token,
        client_id="com.thoughtpins.test",
        post_form=post_ok,
    )

    assert calls[0][0] == APPLE_TOKEN_URL
    assert calls[0][1]["code"] == "one-time-code"
    assert calls[0][1]["redirect_uri"] == "https://app.example.com/app/"
    assert calls[1][0] == APPLE_REVOKE_URL
    assert calls[1][1]["token"] == "apple-refresh-secret"

    def post_failure(url, **_kwargs):
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "secret": "must-not-escape"},
            request=httpx.Request("POST", url),
        )

    try:
        exchange_apple_authorization_code(
            "bad-code",
            client_id="com.thoughtpins.test",
            post_form=post_failure,
        )
    except AppleOAuthError as exc:
        assert "must-not-escape" not in str(exc)
        assert "bad-code" not in str(exc)
    else:
        raise AssertionError("Expected AppleOAuthError")


def test_unverified_provider_email_never_links_an_existing_account(isolated_db):
    from thoughtpins.db import OAuthCredential, User
    from thoughtpins.oauth import OAuthIdentity
    from thoughtpins.oauth_accounts import resolve_oauth_user
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    session = get_session()
    try:
        existing = register_user(
            email="owner@example.com", display_name="Owner", session=session, bypass_system_lock=True
        )
        resolved, credential = resolve_oauth_user(
            session,
            OAuthIdentity(
                provider="google",
                subject="unverified-subject",
                email="owner@example.com",
                email_verified=False,
                audience="google-client",
            ),
            display_name="Different person",
            allow_registration=True,
        )
        session.commit()

        assert resolved.id != existing.id
        assert resolved.email is None
        assert credential.user_id == resolved.id
        assert session.query(User).count() == 2
        assert session.query(OAuthCredential).count() == 1
    finally:
        session.close()


def test_failed_apple_revocation_keeps_account_and_credential_retryable(isolated_db) -> None:
    from fastapi import FastAPI

    from thoughtpins.api_routes.account import create_account_router
    from thoughtpins.db import OAuthCredential, User
    from thoughtpins.oauth_accounts import provider_subject_hash, store_refresh_credential
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    user = register_user(email="apple-retry@example.com")
    session = get_session()
    try:
        credential = OAuthCredential(
            user_id=user.id,
            provider="apple",
            provider_subject_hash=provider_subject_hash("apple", "retry-subject"),
            client_id="com.thoughtpins.test",
        )
        session.add(credential)
        store_refresh_credential(
            credential,
            refresh_token="retryable-refresh-token",
            client_id="com.thoughtpins.test",
        )
        session.commit()
    finally:
        session.close()

    def fail_revocation(_token: str, *, client_id: str) -> None:
        assert client_id == "com.thoughtpins.test"
        raise OSError("provider temporarily unavailable")

    app = FastAPI()
    app.include_router(
        create_account_router(
            current_user_dependency=lambda: user.id,
            current_session_dependency=lambda: None,
            revoke_apple_token_fn=fail_revocation,
        )
    )
    response = TestClient(app).request("DELETE", "/v1/me", json={"confirm": "DELETE"})

    assert response.status_code == 503
    assert "account was not deleted" in response.json()["detail"]
    session = get_session()
    try:
        stored_user = session.query(User).filter(User.id == user.id).one()
        assert stored_user.is_active is True
        assert stored_user.email == "apple-retry@example.com"
        assert session.query(OAuthCredential).filter(OAuthCredential.user_id == user.id).count() == 1
    finally:
        session.close()


def test_apple_login_rejects_nonce_mismatch_before_code_exchange(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.oauth import OAuthIdentity

    private_pem, _ = _apple_signing_key()
    _configure_apple(monkeypatch, private_key=private_pem)
    monkeypatch.setattr(
        "thoughtpins.api.verify_oauth_id_token",
        lambda provider, token: OAuthIdentity(
            provider="apple",
            subject="apple-user-123",
            email="apple@example.com",
            email_verified=True,
            audience="com.thoughtpins.test",
            nonce="expected-nonce-value",
        ),
    )
    exchange_calls: list[str] = []
    monkeypatch.setattr(
        "thoughtpins.api.exchange_apple_authorization_code",
        lambda code, **kwargs: exchange_calls.append(code),
    )

    response = TestClient(app).post(
        "/v1/auth/oauth",
        json={
            "provider": "apple",
            "id_token": "x" * 24,
            "authorization_code": "one-time-code",
            "nonce": "different-nonce-value",
        },
    )

    assert response.status_code == 401
    assert exchange_calls == []


def test_apple_login_rejects_code_bound_to_another_identity(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.apple_oauth import AppleTokenGrant
    from thoughtpins.oauth import OAuthIdentity

    private_pem, _ = _apple_signing_key()
    _configure_apple(monkeypatch, private_key=private_pem)

    def verify(_provider, token):
        return OAuthIdentity(
            provider="apple",
            subject="subject-b" if token == "code-id-token" else "subject-a",
            email="apple@example.com",
            email_verified=True,
            audience="com.thoughtpins.test",
            nonce="nonce-value-for-test",
        )

    monkeypatch.setattr("thoughtpins.api.verify_oauth_id_token", verify)
    monkeypatch.setattr(
        "thoughtpins.api.exchange_apple_authorization_code",
        lambda code, **kwargs: AppleTokenGrant(
            refresh_token="apple-refresh-secret",
            id_token="code-id-token",
        ),
    )

    response = TestClient(app).post(
        "/v1/auth/oauth",
        json={
            "provider": "apple",
            "id_token": "x" * 24,
            "authorization_code": "one-time-code",
            "nonce": "nonce-value-for-test",
        },
    )

    assert response.status_code == 401
    assert "does not match" in response.json()["error"]["message"]


def test_apple_login_stores_only_encrypted_refresh_token_and_deletion_revokes_it(
    isolated_db,
    monkeypatch,
):
    from thoughtpins.api import app
    from thoughtpins.apple_oauth import AppleTokenGrant
    from thoughtpins.db import OAuthCredential, User
    from thoughtpins.oauth import OAuthIdentity
    from thoughtpins.store import get_session

    private_pem, _ = _apple_signing_key()
    _configure_apple(monkeypatch, private_key=private_pem)

    monkeypatch.setattr(
        "thoughtpins.api.verify_oauth_id_token",
        lambda provider, token: OAuthIdentity(
            provider="apple",
            subject="apple-user-123",
            email="apple@example.com",
            email_verified=True,
            audience="com.thoughtpins.test",
            nonce="nonce-value-for-test",
        ),
    )
    monkeypatch.setattr(
        "thoughtpins.api.exchange_apple_authorization_code",
        lambda code, **kwargs: AppleTokenGrant(
            refresh_token="apple-refresh-secret",
            id_token="apple-code-id-token",
        ),
    )
    revoked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "thoughtpins.api.revoke_apple_refresh_token",
        lambda token, *, client_id: revoked.append((token, client_id)),
    )

    client = TestClient(app)
    login = client.post(
        "/v1/auth/oauth",
        json={
            "provider": "apple",
            "id_token": "x" * 24,
            "authorization_code": "one-time-code",
            "nonce": "nonce-value-for-test",
        },
    )
    assert login.status_code == 200, login.text
    access_token = login.json()["access_token"]

    session = get_session()
    try:
        credential = session.query(OAuthCredential).one()
        assert credential.provider_subject_hash != "apple-user-123"
        assert credential.refresh_token_encrypted.startswith("enc:v1:")
        assert "apple-refresh-secret" not in credential.refresh_token_encrypted
        user = session.query(User).filter(User.id == credential.user_id).one()
        assert "oauth_profiles" not in (user.preferences_json or {})
    finally:
        session.close()

    exported = client.get("/v1/export", headers={"Authorization": f"Bearer {access_token}"})
    assert exported.status_code == 200
    assert "oauth_credentials" not in exported.json()["tables"]
    assert "apple-refresh-secret" not in exported.text

    deleted = client.request(
        "DELETE",
        "/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"confirm": "DELETE"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["provider_revocation"] == {"attempted": 1, "revoked": 1, "failed": 0}
    assert revoked == [("apple-refresh-secret", "com.thoughtpins.test")]

    session = get_session()
    try:
        assert session.query(OAuthCredential).count() == 0
    finally:
        session.close()
