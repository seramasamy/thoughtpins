from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient


def test_register_login_and_me(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    register = client.post(
        "/v1/auth/register",
        json={"email": "USER@example.com", "password": "correct horse battery staple"},
    )
    assert register.status_code == 200
    assert register.json()["api_key"].startswith("tp_")

    login = client.post(
        "/v1/auth/login",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    me = client.get("/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_register_and_login_with_phone_identifier(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    register = client.post(
        "/v1/auth/register",
        json={"phone": "+1 (555) 555-0123", "password": "correct horse battery staple"},
    )
    assert register.status_code == 200

    login = client.post(
        "/v1/auth/login",
        json={"identifier": "+15555550123", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    me = client.get("/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["phone"] == "+15555550123"


def test_refresh_rotates_and_logout_revokes_session(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    client.post(
        "/v1/auth/register",
        json={"email": "session@example.com", "password": "correct horse battery staple"},
    )
    login = client.post(
        "/v1/auth/login",
        json={"email": "session@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    original_refresh = login.json()["refresh_token"]

    refresh = client.post("/v1/auth/refresh", json={"refresh_token": original_refresh})
    assert refresh.status_code == 200
    rotated_refresh = refresh.json()["refresh_token"]
    assert rotated_refresh != original_refresh

    replay = client.post("/v1/auth/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401

    logout = client.post("/v1/auth/logout", json={"refresh_token": rotated_refresh})
    assert logout.status_code == 200
    after_logout = client.post("/v1/auth/refresh", json={"refresh_token": rotated_refresh})
    assert after_logout.status_code == 401


def test_entry_endpoint_uses_authenticated_user_scope(isolated_db, monkeypatch):
    from thoughtpins.api import app

    def fake_process_message(session, text, **kwargs):
        assert kwargs["user_id"]
        return {
            "type": "journal_stored",
            "entry_id": "entry123",
            "stats": {"entities": 1, "events": 0, "memories": 1, "relationships": 0},
        }

    monkeypatch.setattr("thoughtpins.api.process_message", fake_process_message)

    client = TestClient(app)
    response = client.post("/v1/entries", json={"text": "Had lunch with Maya."})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["entry_id"] == "entry123"


def test_error_envelope_and_request_id(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    response = client.get("/v1/me", headers={"X-Request-ID": "req-test-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test-1"

    invalid = client.post(
        "/v1/auth/login",
        json={"email": "missing@example.com", "password": ""},
        headers={"X-Request-ID": "req-test-2"},
    )
    assert invalid.status_code == 422
    body = invalid.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["request_id"] == "req-test-2"


def test_daily_recap_report_contract(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    response = client.get("/v1/reports?type=daily")

    assert response.status_code == 200
    body = response.json()
    assert body["report_type"] == "daily"
    assert body["markdown"].startswith("# Daily Recap:")
    assert "**Entries:**" in body["markdown"]
    assert "path" not in body
    assert "user_id" not in body


def test_unexpected_library_error_does_not_expose_internal_details(isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app

    monkeypatch.setattr(
        "thoughtpins.api_routes.library.ingest_document_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret backend path C:/private/store")),
    )

    response = TestClient(app).post("/v1/library", json={"text": "A valid source note."})

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["message"] == "The request could not be completed. Please try again."
    assert "private/store" not in response.text


def test_api_fails_closed_when_distributed_rate_limiter_is_unavailable(isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app
    from thoughtpins.rate_limit import RateLimitBackendUnavailable

    monkeypatch.setattr(
        "thoughtpins.api.check_rate_limit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RateLimitBackendUnavailable()),
    )

    response = TestClient(app).post(
        "/v1/auth/login",
        json={"identifier": "nobody@example.com", "password": "not-a-real-password"},
        headers={"X-Request-ID": "rate-limit-outage"},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json()["error"] == {
        "code": "rate_limit_backend_unavailable",
        "message": "Traffic controls are temporarily unavailable. Please try again.",
        "request_id": "rate-limit-outage",
    }


def test_error_catalog_and_openapi_contract(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    catalog = client.get("/v1/errors")
    assert catalog.status_code == 200
    assert "validation_error" in catalog.json()["codes"]

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    spec = openapi.json()
    assert "ErrorEnvelope" in spec["components"]["schemas"]
    assert "422" in spec["paths"]["/v1/entries"]["post"]["responses"]


def test_client_config_omits_private_adapter_flags(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setattr(config, "ENABLE_TELEGRAM_BOT", True)
    monkeypatch.setattr(config, "TELEGRAM_TEST_MODE", True)
    monkeypatch.setattr(config, "ENABLE_FOUNDER_MODE", True)

    client = TestClient(app)
    response = client.get("/v1/client-config")

    assert response.status_code == 200
    body = response.json()
    assert body["auth_required"] is False
    assert "telegram_enabled" not in body
    assert "telegram_test_mode" not in body
    assert "founder_test_mode_enabled" not in body
    assert body["oauth_google_enabled"] is False
    assert body["memory_context_mode"] in {"smart", "full"}
    assert body["privacy_policy_url"] == "/privacy"
    assert body["terms_url"] == "/terms"
    assert body["account_deletion_url"] == "/account/delete"
    assert body["legal_document_version"] == "2026-07-13"
    assert body["minimum_supported_clients"]["ios"] == "0.0.0"
    assert body["recommended_clients"]["web"]
    assert body["store_urls"]["web"]
    assert "secret-token" not in response.text


def test_public_legal_pages_are_available_without_auth(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    expected = {
        "/privacy": [
            "last updated: July 13, 2026",
            "Contact Info",
            "User Content",
            "cross-app tracking",
            "does not defeat publisher controls",
        ],
        "/terms": ["AI-assisted responses", "support@thoughtpins.com"],
        "/support": ["Security or privacy", "account deletion", "support@thoughtpins.com"],
        "/account/delete": ["Web deletion request", "What deletion removes", "Exports before deletion"],
        "/delete-account": ["Web deletion request", "What deletion removes", "Exports before deletion"],
        "/ai-disclosure": ["Provider-neutral runtime", "Human control", "No professional advice"],
        "/security": ["Tenant isolation", "Responsible disclosure", "Local no-auth sessions"],
    }
    for path, markers in expected.items():
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Thought Pins" in response.text
        for marker in markers:
            assert marker in response.text

    css = client.get("/assets/styles.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert '@import "/assets/styles/' in css.text
    assert '@import "./styles/' not in css.text

    from scripts.web_assets import read_stylesheet_bundle

    root = Path(__file__).resolve().parents[1]
    authored_css = read_stylesheet_bundle(root / "site" / "assets" / "styles.css")
    assert ".shell" in authored_css

    root = client.get("/")
    assert root.status_code == 200
    assert "text/html" in root.headers["content-type"]
    assert "Your memory, connected" in root.text
    # Verify the registration destination without freezing editorial CTA copy.
    assert 'data-primary-cta data-app-link="register" href="/app/?auth=register"' in root.text

    script = client.get("/assets/site.js")
    assert script.status_code == 200
    assert "text/javascript" in script.headers["content-type"]
    assert "auth_required" in script.text

    logo = client.get("/assets/thought-pins-mark.svg")
    assert logo.status_code == 200
    assert "image/svg+xml" in logo.headers["content-type"]
    assert "brain-shaped pin" in logo.text

    manifest = client.get("/assets/site.webmanifest")
    assert manifest.status_code == 200
    assert "application/manifest+json" in manifest.headers["content-type"]

    assert client.get("/robots.txt").status_code == 200
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "https://thoughtpins.com/account/delete" in sitemap.text


def test_preferences_legal_and_device_core(isolated_db, monkeypatch):
    import thoughtpins.api as api_module
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "PRIVATE_ALLOW_LLM", False)
    monkeypatch.setattr(type(config), "PRIVATE_ALLOW_LLM", False)

    client = TestClient(app)
    prefs = client.get("/v1/preferences")
    assert prefs.status_code == 200
    assert prefs.json()["notifications_enabled"] is False
    assert prefs.json()["response_style"] == "friendly"

    blocked_private = client.patch("/v1/preferences", json={"private_entries_in_ask": True})
    assert blocked_private.status_code == 403
    blocked_private_chat = client.post("/v1/chat", json={"text": "What did I write?", "include_private": True})
    assert blocked_private_chat.status_code == 403

    monkeypatch.setattr(config, "PRIVATE_ALLOW_LLM", True)
    monkeypatch.setattr(type(config), "PRIVATE_ALLOW_LLM", True)
    enabled_private = client.patch("/v1/preferences", json={"private_entries_in_ask": True})
    assert enabled_private.status_code == 200

    captured_private: list[bool] = []

    def fake_execute_chat_message(*args, **kwargs):
        captured_private.append(bool(kwargs["include_private"]))
        return SimpleNamespace(
            status="completed",
            route_type="chat",
            reply="Test response",
            entry_id=None,
            job_id=None,
            document_id=None,
            requires_confirmation=False,
            confirmation_prompt=None,
            context_size_chars=0,
            metadata={},
        )

    monkeypatch.setattr(api_module, "execute_chat_message", fake_execute_chat_message)
    assert client.post("/v1/chat", json={"text": "Use my preference"}).status_code == 200
    assert client.post("/v1/chat", json={"text": "Public only", "include_private": False}).status_code == 200
    assert captured_private == [True, False]

    updated = client.patch(
        "/v1/preferences",
        json={
            "notifications_enabled": True,
            "reminder_hour_local": 9,
            "timezone": "America/New_York",
            "preferred_name": "Test User",
            "response_style": "clear",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["notifications_enabled"] is True
    assert updated.json()["reminder_hour_local"] == 9
    assert updated.json()["preferred_name"] == "Test User"
    assert updated.json()["response_style"] == "clear"

    invalid_style = client.patch("/v1/preferences", json={"response_style": "unbounded"})
    assert invalid_style.status_code == 422

    accepted = client.post("/v1/legal/acceptances", json={"document": "privacy", "version": "2026-05-23"})
    assert accepted.status_code == 200
    assert accepted.json()["legal_acceptances"]["privacy"]["version"] == "2026-05-23"

    device = client.post(
        "/v1/devices",
        json={
            "installation_id": "web-test-install",
            "platform": "web",
            "device_name": "Browser",
            "app_version": "0.2.0",
            "build_number": "local",
            "push_provider": "webpush",
            "push_token": "x" * 32,
            "notifications_enabled": True,
            "metadata": {"timezone": "America/New_York"},
        },
    )
    assert device.status_code == 200
    assert device.json()["push_token_present"] is True
    assert "push_token_hash" not in device.text
    assert "push_token_encrypted" not in device.text

    listed = client.get("/v1/devices")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["installation_id"] == "web-test-install"

    exported = client.get("/v1/export")
    assert exported.status_code == 200
    app_devices = exported.json()["tables"]["app_devices"]
    assert len(app_devices) == 1
    assert "push_token_hash" not in app_devices[0]
    assert "push_token_encrypted" not in app_devices[0]

    revoked = client.delete("/v1/devices/web-test-install")
    assert revoked.status_code == 200
    assert revoked.json()["notifications_enabled"] is False
    assert revoked.json()["push_token_present"] is False
    assert revoked.json()["revoked_at_utc"]


def test_backend_serves_static_frontend_without_auth(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    page = client.get("/app")
    fallback = client.get("/app/entries")

    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Thought Pins" in page.text
    assert 'src="/app/' in page.text or 'src="/src/' in page.text
    assert fallback.status_code == 200
    assert "Thought Pins" in fallback.text


def test_frontend_dist_bundle_takes_precedence_over_static_fallback(monkeypatch):
    from thoughtpins.api_routes import public
    from thoughtpins.config import config

    app_root = Path(__file__).resolve().parents[1] / ".tmp" / f"frontend-resolver-{uuid4().hex}"
    dist = app_root / "frontend" / "dist"
    static = app_root / "frontend" / "static"
    dist.mkdir(parents=True)
    static.mkdir(parents=True)
    (dist / "index.html").write_text("dist build", encoding="utf-8")
    (dist / ".thoughtpins-build.json").write_text("{}", encoding="utf-8")
    (static / "index.html").write_text("static fallback", encoding="utf-8")

    monkeypatch.setattr(config, "resolve_path", lambda path: (app_root / path).resolve())

    assert public._resolve_frontend_dir() == dist.resolve()


def test_maintenance_mode_keeps_public_surfaces_available_and_blocks_mutations(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    config_cls = type(config)
    monkeypatch.setattr(config, "MAINTENANCE_MODE", True)
    monkeypatch.setattr(config_cls, "MAINTENANCE_MODE", True)
    monkeypatch.setattr(config, "MAINTENANCE_MESSAGE", "Maintenance currently. Please try again soon.")
    monkeypatch.setattr(config_cls, "MAINTENANCE_MESSAGE", "Maintenance currently. Please try again soon.")
    monkeypatch.setattr(config, "MAINTENANCE_RETRY_AFTER_SECONDS", 123)
    monkeypatch.setattr(config_cls, "MAINTENANCE_RETRY_AFTER_SECONDS", 123)
    monkeypatch.setattr(config, "MAINTENANCE_ALLOW_READS", True)
    monkeypatch.setattr(config_cls, "MAINTENANCE_ALLOW_READS", True)

    client = TestClient(app)

    page = client.get("/app")
    assert page.status_code == 200
    assert "Thought Pins" in page.text

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["maintenance_mode"] is True

    client_config = client.get("/v1/client-config")
    assert client_config.status_code == 200
    assert client_config.json()["maintenance_mode"] is True
    assert client_config.json()["maintenance_retry_after_seconds"] == 123

    blocked_chat = client.post("/v1/chat", json={"text": "hello"})
    assert blocked_chat.status_code == 503
    assert blocked_chat.headers["Retry-After"] == "123"
    assert blocked_chat.json()["error"]["code"] == "maintenance_mode"
    assert "Maintenance currently" in blocked_chat.json()["error"]["message"]

    blocked_login = client.post(
        "/v1/auth/login", json={"identifier": "review@example.com", "password": "correct horse battery staple"}
    )
    assert blocked_login.status_code == 503
    assert blocked_login.json()["error"]["code"] == "maintenance_mode"


def test_security_headers_request_id_and_body_limit(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "MAX_REQUEST_BODY_BYTES", 20)
    monkeypatch.setattr(type(config), "MAX_REQUEST_BODY_BYTES", 20)

    client = TestClient(app)
    health = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
    assert health.status_code == 200
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["X-Request-ID"] != "bad id with spaces"

    too_large = client.post("/v1/entries", json={"text": "x" * 100})
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "payload_too_large"


def test_register_rejects_weak_password_and_bad_email(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    bad_email = client.post("/v1/auth/register", json={"email": "not-an-email", "password": "long enough pass"})
    assert bad_email.status_code == 422

    weak_password = client.post("/v1/auth/register", json={"email": "weak@example.com", "password": "shortpass"})
    assert weak_password.status_code == 422


def test_register_can_hide_permanent_api_key(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "RETURN_API_KEY_ON_REGISTER", False)
    monkeypatch.setattr(type(config), "RETURN_API_KEY_ON_REGISTER", False)

    client = TestClient(app)
    response = client.post(
        "/v1/auth/register",
        json={"email": "nokey@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    assert response.json()["api_key"] is None


def test_user_api_keys_can_be_disabled(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(type(config), "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(config, "ALLOW_USER_API_KEYS", False)
    monkeypatch.setattr(type(config), "ALLOW_USER_API_KEYS", False)

    client = TestClient(app)
    register = client.post(
        "/v1/auth/register",
        json={"email": "apikey@example.com", "password": "correct horse battery staple"},
    )
    api_key = register.json()["api_key"]

    blocked = client.get("/v1/me", headers={"X-API-Key": api_key})
    assert blocked.status_code == 401


def test_private_entries_are_encrypted_at_rest(isolated_db, monkeypatch):
    from cryptography.fernet import Fernet

    from thoughtpins.config import config
    from thoughtpins.crypto import ENCRYPTED_PREFIX, maybe_decrypt_text
    from thoughtpins.db import RawEntry
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", key)
    monkeypatch.setattr(type(config), "DATA_ENCRYPTION_KEY", key)
    monkeypatch.setattr(config, "PRIVATE_ALLOW_LLM", False)
    monkeypatch.setattr(type(config), "PRIVATE_ALLOW_LLM", False)

    user = register_user(email="private@example.com")
    session = get_session()
    try:
        result = process_message(session, "private launch note", user_id=user.id, is_private=True)
        assert result["type"] == "private_stored"
        entry = session.query(RawEntry).filter(RawEntry.id == result["entry_id"]).first()
        assert entry.raw_text.startswith(ENCRYPTED_PREFIX)
        assert "private launch note" not in entry.raw_text
        assert maybe_decrypt_text(entry.raw_text) == "private launch note"
    finally:
        session.close()


def test_deep_health_reports_runtime_dependencies(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    response = client.get("/v1/health/deep")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["db"]["status"] == "ok"
    assert body["checks"]["worker"]["status"] == "ok"
    assert body["checks"]["llm"]["configured"] is True
    assert "model" not in body["checks"]["llm"]
    assert "provider" not in body["checks"]["llm"]
    assert body["checks"]["article_fetch"]["status"] == "configured"
    assert "vector" in body["checks"]
    assert "jobs" in body["checks"]


def test_deep_health_warns_for_optional_local_redis(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(type(config), "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "INGESTION_QUEUE_BACKEND", "thread")
    monkeypatch.setattr(type(config), "INGESTION_QUEUE_BACKEND", "thread")
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(type(config), "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(config, "REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(type(config), "REDIS_URL", "redis://127.0.0.1:1/0")

    # This test is about Redis being optional, so the unrelated checks are
    # pinned. Otherwise the overall status depends on whatever the machine
    # happens to have configured: with no .env present, the default local
    # transcription and vector settings degrade it and the assertion below
    # fails for a reason that has nothing to do with Redis.
    from thoughtpins import runtime_health

    for probe in ("llm_health", "vector_health", "article_fetch_health", "transcription_health", "worker_health"):
        monkeypatch.setattr(runtime_health, probe, lambda: {"status": "ok"})

    client = TestClient(app)
    response = client.get("/v1/health/deep")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "warn"
    assert body["checks"]["redis"]["required"] is False


def test_public_readiness_is_minimal_and_returns_503_for_dependency_failure(isolated_db, monkeypatch):
    from thoughtpins.api import app

    monkeypatch.setattr(
        "thoughtpins.api_routes.metadata.build_readiness_checks",
        lambda: {
            "db": {"status": "ok", "detail": "must not be public"},
            "redis": {"status": "error", "detail": "internal endpoint"},
            "worker": {"status": "ok"},
            "vector": {"status": "configured"},
        },
    )

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"db": "ok", "redis": "error", "worker": "ok", "vector": "configured"},
    }
    assert "detail" not in response.text


def test_public_readiness_fails_closed_when_dependency_checks_time_out(isolated_db, monkeypatch):
    from thoughtpins.api import app

    async def time_out(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr("thoughtpins.api_routes.metadata.run_in_threadpool", time_out)

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"runtime": "timeout"}}


def test_job_list_retry_and_cancel(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.db import IngestionJob
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    queued: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "thoughtpins.api.enqueue_ingestion_job", lambda job_id, user_id=None: queued.append((job_id, user_id))
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        failed = IngestionJob(user_id=user.id, raw_text="retry me", source="api", status="failed", error="boom")
        pending = IngestionJob(user_id=user.id, raw_text="cancel me", source="api", status="pending")
        session.add_all([failed, pending])
        session.commit()
        failed_id = failed.id
        pending_id = pending.id
        user_id = user.id
    finally:
        session.close()

    client = TestClient(app)
    listed = client.get("/v1/jobs?status=failed")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == failed_id

    retried = client.post(f"/v1/jobs/{failed_id}/retry")
    assert retried.status_code == 202
    assert retried.json()["status"] == "queued"
    assert queued == [(failed_id, user_id)]

    canceled = client.post(f"/v1/jobs/{pending_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


def test_oauth_login_creates_user_when_enabled(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.oauth import OAuthIdentity

    def fake_verify(provider, token):
        assert provider == "google"
        assert token == "x" * 24
        return OAuthIdentity(provider="google", subject="sub123", email="oauth@example.com", email_verified=True)

    monkeypatch.setattr("thoughtpins.api.verify_oauth_id_token", fake_verify)
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ALLOW_OAUTH_REGISTRATION", True)
    monkeypatch.setattr(type(config), "ALLOW_OAUTH_REGISTRATION", True)

    client = TestClient(app)
    response = client.post("/v1/auth/oauth", json={"provider": "google", "id_token": "x" * 24})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_email_verification_blocks_login_when_required(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    monkeypatch.setattr(type(config), "REQUIRE_EMAIL_VERIFICATION", True)

    client = TestClient(app)
    register = client.post(
        "/v1/auth/register",
        json={"email": "verify@example.com", "password": "correct horse battery staple"},
    )
    assert register.status_code == 200
    token = register.json()["verification_token"]
    assert token

    blocked = client.post(
        "/v1/auth/login",
        json={"email": "verify@example.com", "password": "correct horse battery staple"},
    )
    assert blocked.status_code == 403

    verified = client.post("/v1/auth/email/verify", json={"email": "verify@example.com", "token": token})
    assert verified.status_code == 200

    login = client.post(
        "/v1/auth/login",
        json={"email": "verify@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200


def test_entries_pagination_and_status(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        first_id = ""
        for index in range(3):
            entry = RawEntry(
                user_id=user.id,
                raw_text=f"Entry {index}",
                content_hash=hash_text(f"Entry {index}"),
                processed_status="completed",
            )
            session.add(entry)
            session.flush()
            first_id = first_id or entry.id
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    page = client.get("/v1/entries?page=1&limit=2")
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert page.json()["has_next"] is True

    status = client.get(f"/v1/entries/{first_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"


def test_memory_cards_group_entities_with_statline(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import Entity, EntityMention, Memory, RawEntry, Relationship
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        entry = RawEntry(
            user_id=user.id,
            raw_text="Met Maya at Lumen and discussed the launch checklist.",
            content_hash=hash_text("Met Maya at Lumen and discussed the launch checklist."),
            processed_status="completed",
        )
        maya = Entity(user_id=user.id, type="person", canonical_name="Maya")
        lumen = Entity(user_id=user.id, type="place", canonical_name="Lumen")
        session.add_all([entry, maya, lumen])
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=entry.id,
                memory_type="conversation",
                subject_entity_id=maya.id,
                object_entity_id=lumen.id,
                text="Maya liked Lumen for serious product conversations.",
            )
        )
        session.add(EntityMention(user_id=user.id, raw_entry_id=entry.id, entity_id=maya.id, surface_text="Maya"))
        session.add(
            Relationship(
                user_id=user.id,
                source_entity_id=maya.id,
                target_entity_id=lumen.id,
                relation_type="met_at",
                raw_entry_id=entry.id,
                evidence_count=2,
            )
        )
        entry_id = entry.id
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    response = client.get("/v1/memory/cards?section=people")

    assert response.status_code == 200
    body = response.json()
    assert body["section"] == "people"
    assert body["query"] == ""
    assert body["items"][0]["name"] == "Maya"
    assert body["items"][0]["recent_memories"][0]["entry_id"] == entry_id
    assert body["items"][0]["statline"]["MEM"] == 1
    assert body["items"][0]["statline"]["MENT"] == 1
    assert body["items"][0]["statline"]["REL"] == 1
    assert body["items"][0]["relationships"][0]["other"] == "Lumen"

    searched = client.get("/v1/memory/cards?section=all&q=maya")
    assert searched.status_code == 200
    assert searched.json()["query"] == "maya"
    assert searched.json()["items"][0]["id"] == body["items"][0]["id"]

    detail = client.get(f"/v1/memory/cards/{body['items'][0]['id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["name"] == "Maya"
    assert detail_body["all_memories"][0]["text"] == "Maya liked Lumen for serious product conversations."
    assert detail_body["entries"][0]["raw_text"] == "Met Maya at Lumen and discussed the launch checklist."


def test_safety_report_endpoint_records_report_and_audit(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import AuditLog, SafetyReport
    from thoughtpins.store import get_session

    client = TestClient(app)
    client.post(
        "/v1/auth/register",
        json={"email": "safety@example.com", "password": "correct horse battery staple"},
    )
    login = client.post(
        "/v1/auth/login",
        json={"identifier": "safety@example.com", "password": "correct horse battery staple"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/v1/safety/reports",
        headers=headers,
        json={
            "category": "unsafe_ai_output",
            "summary": "The assistant produced an unsafe response in chat.",
            "target_type": "general",
            "source": "web",
            "metadata": {"surface": "legal", "text": "do not duplicate report text"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "received"
    assert body["support_channel"] == "support@thoughtpins.com"

    session = get_session()
    try:
        report = session.query(SafetyReport).filter(SafetyReport.id == body["id"]).one()
        assert report.category == "unsafe_ai_output"
        assert report.summary == "The assistant produced an unsafe response in chat."
        assert report.metadata_json["client_metadata"] == {"surface": "legal"}
        audit = session.query(AuditLog).filter(AuditLog.action == "safety.report.created").one()
        assert audit.metadata_json["report_id"] == report.id
        assert "summary" not in audit.metadata_json
    finally:
        session.close()

    export = client.get("/v1/export", headers=headers)
    assert export.status_code == 200
    assert export.json()["tables"]["safety_reports"][0]["id"] == body["id"]


def test_safety_report_rejects_cross_tenant_target(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    client = TestClient(app)
    client.post(
        "/v1/auth/register",
        json={"email": "target-owner@example.com", "password": "correct horse battery staple"},
    )
    owner_login = client.post(
        "/v1/auth/login",
        json={"identifier": "target-owner@example.com", "password": "correct horse battery staple"},
    )
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
    owner = client.get("/v1/me", headers=owner_headers).json()

    session = get_session()
    try:
        entry = RawEntry(
            user_id=owner["id"],
            raw_text="A private safety report target.",
            content_hash=hash_text("A private safety report target."),
            processed_status="completed",
        )
        session.add(entry)
        session.commit()
        target_id = entry.id
    finally:
        session.close()

    client.post(
        "/v1/auth/register",
        json={"email": "other-user@example.com", "password": "correct horse battery staple"},
    )
    other_login = client.post(
        "/v1/auth/login",
        json={"identifier": "other-user@example.com", "password": "correct horse battery staple"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    blocked = client.post(
        "/v1/safety/reports",
        headers=other_headers,
        json={
            "category": "privacy_concern",
            "summary": "This target belongs to another account.",
            "target_type": "raw_entry",
            "target_id": target_id,
        },
    )
    assert blocked.status_code == 404

    allowed = client.post(
        "/v1/safety/reports",
        headers=owner_headers,
        json={
            "category": "privacy_concern",
            "summary": "This target belongs to my account.",
            "target_type": "raw_entry",
            "target_id": target_id,
        },
    )
    assert allowed.status_code == 201


def test_account_export_and_delete_removes_user_data(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import Memory, RawEntry, SafetyReport
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    client = TestClient(app)
    register = client.post(
        "/v1/auth/register",
        json={"email": "export@example.com", "password": "correct horse battery staple"},
    )
    user_id = register.json()["user_id"]
    login = client.post(
        "/v1/auth/login",
        json={"email": "export@example.com", "password": "correct horse battery staple"},
    )
    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    session = get_session()
    try:
        entry = RawEntry(
            user_id=user_id,
            raw_text="Export this memory.",
            content_hash=hash_text("Export this memory."),
            processed_status="completed",
        )
        session.add(entry)
        session.flush()
        session.add(Memory(user_id=user_id, raw_entry_id=entry.id, memory_type="thought", text="Exported memory"))
        session.add(SafetyReport(user_id=user_id, category="other", source="api", summary="Export this safety report."))
        session.commit()
    finally:
        session.close()

    export = client.get("/v1/export", headers=headers)
    assert export.status_code == 200
    assert len(export.json()["tables"]["raw_entries"]) == 1
    assert len(export.json()["tables"]["safety_reports"]) == 1
    assert "api_key" not in export.json()["user"]

    deleted = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["raw_entries"] == 1
    assert deleted.json()["deleted"]["memories"] == 1
    assert deleted.json()["deleted"]["safety_reports"] == 1

    me = client.get("/v1/me", headers=headers)
    assert me.status_code == 401


def test_account_export_strips_internal_hashes_and_verification_tokens(isolated_db):
    from thoughtpins.auth import hash_password
    from thoughtpins.data_lifecycle import export_user_data
    from thoughtpins.db import RawEntry, User
    from thoughtpins.email_verification import create_email_verification_token
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user
    from thoughtpins.utils import hash_text

    raw_text = "Export the human-readable memory, not internal hashes."
    content_hash = hash_text(raw_text)
    user = register_user(
        email="export-hashes@example.com",
        password_hash=hash_password("correct horse battery staple"),
    )
    session = get_session()
    try:
        db_user = session.query(User).filter(User.id == user.id).one()
        verification_token = create_email_verification_token(db_user)
        entry = RawEntry(
            user_id=user.id,
            raw_text=raw_text,
            content_hash=content_hash,
            processed_status="completed",
        )
        session.add(entry)
        session.commit()

        payload = export_user_data(session, user.id)
        encoded = json.dumps(payload, sort_keys=True)

        assert payload["tables"]["raw_entries"][0]["raw_text"] == raw_text
        assert payload["user"]["preferences_json"]["email_verification"]["verified"] is False
        for internal in [
            "password_hash",
            "api_key",
            "token_hash",
            "content_hash",
            "push_token_hash",
            "push_token_encrypted",
            verification_token,
            content_hash,
        ]:
            assert internal not in encoded
    finally:
        session.close()


def test_account_delete_fails_closed_when_vector_cleanup_fails(isolated_db, monkeypatch):
    import pytest

    from thoughtpins.auth import hash_password
    from thoughtpins.data_lifecycle import DataDeletionUnavailable, delete_user_data
    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user
    from thoughtpins.utils import hash_text

    class BrokenVectorStore:
        def delete(self, ids):
            raise RuntimeError("vector backend unavailable")

    monkeypatch.setattr("thoughtpins.memory.vector_store.get_vector_store", lambda: BrokenVectorStore())

    user = register_user(email="delete-vector@example.com", password_hash=hash_password("correct horse battery staple"))
    session = get_session()
    try:
        entry = RawEntry(
            user_id=user.id,
            raw_text="Keep the account retryable if vector cleanup fails.",
            content_hash=hash_text("Keep the account retryable if vector cleanup fails."),
            processed_status="completed",
        )
        session.add(entry)
        session.flush()
        memory = Memory(
            user_id=user.id, raw_entry_id=entry.id, memory_type="thought", text="Vector cleanup should fail"
        )
        session.add(memory)
        session.commit()

        with pytest.raises(DataDeletionUnavailable, match="account was not deleted"):
            delete_user_data(session, user.id)

        session.expire_all()
        stored_user = session.query(User).filter(User.id == user.id).one()
        assert stored_user.is_active is True
        assert stored_user.email == "delete-vector@example.com"
        assert session.query(Memory).filter(Memory.user_id == user.id).count() == 1
    finally:
        session.close()
