from __future__ import annotations


def _review_secret_for_test() -> str:
    return "review-" + "seed-" + "test-" + "only"


def test_review_seed_creates_login_ready_demo_account(isolated_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins.config import config
    from thoughtpins.review_seed import seed_review_account
    from thoughtpins.store import get_session

    monkeypatch.setattr(config, "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(type(config), "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(config, "JWT_SECRET", "review-seed-test-jwt-secret-32chars")
    monkeypatch.setattr(type(config), "JWT_SECRET", "review-seed-test-jwt-secret-32chars")
    monkeypatch.setattr(config, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(type(config), "VAULT_PATH", tmp_path / "vault")

    secret_for_test = _review_secret_for_test()

    session = get_session()
    try:
        result = seed_review_account(
            email="review@example.com",
            password=secret_for_test,
            export_vault=True,
            package_vault_zip=True,
            session=session,
        )
        assert result.email == "review@example.com"
        assert result.entries >= 2
        assert result.entities >= 6
        assert result.memories >= 3
        assert result.documents == 1
        assert result.chat_messages == 2
        assert result.vault_files and result.vault_files >= 10
        assert result.vault_validation_errors == 0
        assert result.vault_zip_path
    finally:
        session.close()

    from thoughtpins.api import app

    client = TestClient(app)
    login = client.post("/v1/auth/login", json={"email": "review@example.com", "password": secret_for_test})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "review@example.com"

    memory = client.get("/v1/memory/cards?section=people&q=Maya", headers=headers)
    assert memory.status_code == 200
    items = memory.json()["items"]
    assert items
    assert items[0]["name"] == "Maya"
    assert items[0]["obsidian_path"] == "People/Maya.md"
    assert "copper lantern" in items[0]["recent_memories"][0]["text"].lower()

    library = client.get("/v1/library?limit=5", headers=headers)
    assert library.status_code == 200
    assert library.json()[0]["title"] == "Review Article - Attention and Recall"

    export = client.get("/v1/export", headers=headers)
    assert export.status_code == 200
    tables = export.json()["tables"]
    assert tables["raw_entries"]
    assert tables["document_sources"]
    assert tables["chat_messages"]

    deleted = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["raw_entries"] >= 2


def test_review_seed_admits_the_reviewer_through_the_closed_beta_gate(isolated_db, tmp_path, monkeypatch):
    """The demo account has to reach the product, not the invite wall.

    Production runs INVITE_ONLY=true so the public site stays closed. The seed
    used to ignore that entirely, so App Review would have signed in with the
    supplied credentials and been shown a gate — a Guideline 2.1 rejection with
    the app never actually reviewed. Logging in successfully is not the
    assertion that matters; reaching a gated endpoint is.
    """
    from fastapi.testclient import TestClient

    from thoughtpins.config import config
    from thoughtpins.review_seed import seed_review_account
    from thoughtpins.store import get_session

    for attribute, value in (
        ("REQUIRE_API_AUTH", True),
        ("JWT_SECRET", "review-seed-test-jwt-secret-32chars"),
        ("VAULT_PATH", tmp_path / "vault"),
        ("INVITE_ONLY", True),
    ):
        monkeypatch.setattr(config, attribute, value)
        monkeypatch.setattr(type(config), attribute, value)

    secret_for_test = _review_secret_for_test()

    session = get_session()
    try:
        result = seed_review_account(
            email="review@example.com",
            password=secret_for_test,
            session=session,
        )
        assert result.invite_admitted is True, "the seed must admit the review account while the gate is on"
    finally:
        session.close()

    from thoughtpins.api import app

    client = TestClient(app)
    login = client.post("/v1/auth/login", json={"email": "review@example.com", "password": secret_for_test})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # A gated route, not /v1/me: the invite check runs in middleware for every
    # path that is not deliberately exempt, so an exempt route would pass here
    # while the reviewer still could not open the app.
    cards = client.get("/v1/memory/cards?section=people", headers=headers)
    assert cards.status_code == 200, cards.text

    status = client.get("/v1/invites/status", headers=headers)
    if status.status_code == 200:
        body = status.json()
        assert body["invite_required"] is True, "the gate must stay on for everyone else"
        assert body["admitted"] is True


def test_a_normal_account_still_meets_the_gate(isolated_db, tmp_path, monkeypatch):
    """The reviewer's admission must not be a hole for everybody.

    Admission is a redeemed single-use invite rather than a flag that skips the
    check, so this proves the check still exists for an account that has not
    redeemed one.
    """
    from fastapi.testclient import TestClient

    from thoughtpins.config import config

    for attribute, value in (
        ("REQUIRE_API_AUTH", True),
        ("JWT_SECRET", "review-seed-test-jwt-secret-32chars"),
        ("VAULT_PATH", tmp_path / "vault"),
        ("INVITE_ONLY", True),
    ):
        monkeypatch.setattr(config, attribute, value)
        monkeypatch.setattr(type(config), attribute, value)

    from thoughtpins.api import app

    client = TestClient(app)
    registered = client.post(
        "/v1/auth/register",
        json={"email": "outsider@example.com", "password": _review_secret_for_test()},
    )
    assert registered.status_code in {200, 201}, registered.text

    login = client.post(
        "/v1/auth/login",
        json={"email": "outsider@example.com", "password": _review_secret_for_test()},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    blocked = client.get("/v1/memory/cards?section=people", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "invite_required"


def test_review_seed_refuses_production_by_default(isolated_db, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.review_seed import seed_review_account

    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(type(config), "ENVIRONMENT", "production")

    secret_for_test = _review_secret_for_test()

    try:
        seed_review_account(email="review@example.com", password=secret_for_test)
    except RuntimeError as exc:
        assert "Refusing to seed review data in production" in str(exc)
    else:
        raise AssertionError("seed_review_account should refuse production by default")
