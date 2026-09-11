"""Every sign-in method points at one account, and gaining a password is proved.

The promise being tested: however an account was created, it can get in by any
method that address supports, and a password can be added later. The constraint
being tested alongside it: an account that has never had a password must re-prove
control of its inbox before gaining one, because a password outlives the session
that created it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

FIRST_PASSPHRASE = "correct horse battery staple"
SECOND_PASSPHRASE = "another long enough passphrase"


@pytest.fixture
def magic_link_enabled(monkeypatch):
    from thoughtpins.config import config

    monkeypatch.setattr(config, "MAGIC_LINK_ENABLED", True)
    monkeypatch.setattr(config, "MAGIC_LINK_ALLOW_REGISTRATION", True)
    monkeypatch.setattr(config, "SYSTEM_LOCKED", False)
    monkeypatch.setattr(config, "EMAIL_PROVIDER", "none")
    return config


@pytest.fixture
def issued(monkeypatch) -> list:
    """Capture (token, code) pairs as issued; delivery is off, so no inbox."""
    from thoughtpins import magic_link

    captured: list = []
    original = magic_link.issue_magic_link

    def spy(session, email, **kwargs):
        pair = original(session, email, **kwargs)
        captured.append(pair)
        return pair

    monkeypatch.setattr(magic_link, "issue_magic_link", spy)
    monkeypatch.setattr("thoughtpins.api_routes.auth.issue_magic_link", spy)
    return captured


@pytest.fixture
def client(isolated_db):
    from thoughtpins.api import app

    return TestClient(app)


@pytest.fixture
def require_api_auth(monkeypatch):
    """The test database runs open by default; these routes are not public."""
    from thoughtpins.config import config

    monkeypatch.setattr(config, "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(type(config), "REQUIRE_API_AUTH", True)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fresh_code(client: TestClient, issued: list, email: str) -> str:
    assert client.post("/v1/auth/magic-link/request", json={"email": email}).status_code == 200
    return issued[-1][1]


def _sign_in_by_code(client: TestClient, issued: list, email: str) -> str:
    code = _fresh_code(client, issued, email)
    response = client.post("/v1/auth/magic-code/consume", json={"email": email, "code": code})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _register_with_password(client: TestClient, email: str) -> str:
    assert client.post("/v1/auth/register", json={"email": email, "password": FIRST_PASSPHRASE}).status_code == 200
    response = client.post("/v1/auth/login", json={"email": email, "password": FIRST_PASSPHRASE})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


# --------------------------------------------------------------------------
# One account, reachable by every method that its address supports
# --------------------------------------------------------------------------


def test_password_account_can_also_sign_in_by_code(client, magic_link_enabled, issued):
    _register_with_password(client, "both@example.com")

    token = _sign_in_by_code(client, issued, "both@example.com")
    assert client.get("/v1/me", headers=_auth(token)).json()["email"] == "both@example.com"


def test_every_method_reaches_the_same_account_row(client, magic_link_enabled, issued):
    """Three sign-in methods must not create three accounts."""
    password_token = _register_with_password(client, "same@example.com")
    code_token = _sign_in_by_code(client, issued, "same@example.com")

    assert client.post("/v1/auth/magic-link/request", json={"email": "same@example.com"}).status_code == 200
    link_response = client.post("/v1/auth/magic-link/consume", json={"token": issued[-1][0]})
    assert link_response.status_code == 200, link_response.text
    link_token = link_response.json()["access_token"]

    ids = {
        client.get("/v1/me", headers=_auth(token)).json()["id"] for token in (password_token, code_token, link_token)
    }
    assert len(ids) == 1


def test_oauth_account_can_also_sign_in_by_code(client, magic_link_enabled, issued, monkeypatch):
    """Signing up with Google must not lock the address out of link or code."""
    google_token = _sign_in_with_google(client, monkeypatch, "google-user@example.com")
    code_token = _sign_in_by_code(client, issued, "google-user@example.com")

    google_id = client.get("/v1/me", headers=_auth(google_token)).json()["id"]
    code_id = client.get("/v1/me", headers=_auth(code_token)).json()["id"]
    assert google_id == code_id


# --------------------------------------------------------------------------
# What the account reports about itself
# --------------------------------------------------------------------------


def test_sign_in_methods_describes_a_password_account(client, magic_link_enabled, issued):
    token = _register_with_password(client, "described@example.com")

    body = client.get("/v1/account/sign-in-methods", headers=_auth(token)).json()
    assert body["email"] == "described@example.com"
    assert body["password_set"] is True
    assert body["magic_link_available"] is True
    assert body["oauth_providers"] == []
    assert body["password_change_requires"] == "current_password"


def test_sign_in_methods_describes_a_link_only_account(client, magic_link_enabled, issued):
    token = _sign_in_by_code(client, issued, "linkonly@example.com")

    body = client.get("/v1/account/sign-in-methods", headers=_auth(token)).json()
    assert body["password_set"] is False
    assert body["password_change_requires"] == "email_code"


def test_sign_in_methods_lists_linked_providers(client, magic_link_enabled, issued, monkeypatch):
    token = _sign_in_with_google(client, monkeypatch, "provider@example.com")

    body = client.get("/v1/account/sign-in-methods", headers=_auth(token)).json()
    assert body["oauth_providers"] == ["google"]
    assert body["password_change_requires"] == "email_code"


def test_sign_in_methods_requires_authentication(client, require_api_auth):
    assert client.get("/v1/account/sign-in-methods").status_code == 401


# --------------------------------------------------------------------------
# Adding a password to an account that never had one
# --------------------------------------------------------------------------


def test_link_account_adds_password_with_fresh_code_then_signs_in_with_it(client, magic_link_enabled, issued):
    token = _sign_in_by_code(client, issued, "adds@example.com")
    code = _fresh_code(client, issued, "adds@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": code},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["password_set"] is True

    login = client.post("/v1/auth/login", json={"email": "adds@example.com", "password": SECOND_PASSPHRASE})
    assert login.status_code == 200, login.text


def test_session_alone_cannot_add_a_password(client, magic_link_enabled, issued):
    """The security requirement: a borrowed session must not mint a credential."""
    token = _sign_in_by_code(client, issued, "nocode@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE},
        headers=_auth(token),
    )
    assert response.status_code == 403
    assert (
        client.post("/v1/auth/login", json={"email": "nocode@example.com", "password": SECOND_PASSPHRASE}).status_code
        == 401
    )


def test_wrong_code_cannot_add_a_password(client, magic_link_enabled, issued):
    token = _sign_in_by_code(client, issued, "wrongcode@example.com")
    code = _fresh_code(client, issued, "wrongcode@example.com")
    wrong = "000000" if code != "000000" else "111111"

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": wrong},
        headers=_auth(token),
    )
    assert response.status_code == 403


def test_a_consumed_code_cannot_be_replayed_to_add_a_password(client, magic_link_enabled, issued):
    """The code that signed the person in is spent; adding a password needs a new one."""
    code = _fresh_code(client, issued, "replay@example.com")
    signin = client.post("/v1/auth/magic-code/consume", json={"email": "replay@example.com", "code": code})
    token = signin.json()["access_token"]

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": code},
        headers=_auth(token),
    )
    assert response.status_code == 403


def test_another_addresss_code_cannot_add_a_password(client, magic_link_enabled, issued):
    token = _sign_in_by_code(client, issued, "victim@example.com")
    stranger_code = _fresh_code(client, issued, "stranger@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": stranger_code},
        headers=_auth(token),
    )
    assert response.status_code == 403


def test_google_account_adds_password_with_code_and_keeps_google(client, magic_link_enabled, issued, monkeypatch):
    token = _sign_in_with_google(client, monkeypatch, "bothways@example.com")
    code = _fresh_code(client, issued, "bothways@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": code},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text

    assert (
        client.post("/v1/auth/login", json={"email": "bothways@example.com", "password": SECOND_PASSPHRASE}).status_code
        == 200
    )
    still_google = _sign_in_with_google(client, monkeypatch, "bothways@example.com")
    body = client.get("/v1/account/sign-in-methods", headers=_auth(still_google)).json()
    assert body["oauth_providers"] == ["google"]
    assert body["password_set"] is True


def test_account_without_an_email_cannot_set_a_password(client, magic_link_enabled, issued):
    """No inbox means no way to prove anything, so the route says so plainly."""
    from thoughtpins.store import get_session
    from thoughtpins.users import get_user_by_email

    token = _sign_in_by_code(client, issued, "willclear@example.com")
    session = get_session()
    try:
        user = get_user_by_email("willclear@example.com", session=session)
        assert user is not None
        user.email = None
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": "123456"},
        headers=_auth(token),
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------
# Changing a password that already exists
# --------------------------------------------------------------------------


def test_changing_a_password_requires_the_current_one(client, magic_link_enabled, issued):
    token = _register_with_password(client, "changer@example.com")

    rejected = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "current_password": "not the password"},
        headers=_auth(token),
    )
    assert rejected.status_code == 403

    accepted = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "current_password": FIRST_PASSPHRASE},
        headers=_auth(token),
    )
    assert accepted.status_code == 200, accepted.text
    assert (
        client.post("/v1/auth/login", json={"email": "changer@example.com", "password": FIRST_PASSPHRASE}).status_code
        == 401
    )
    assert (
        client.post("/v1/auth/login", json={"email": "changer@example.com", "password": SECOND_PASSPHRASE}).status_code
        == 200
    )


def test_a_code_cannot_stand_in_for_a_known_password(client, magic_link_enabled, issued):
    """An account with a password proves itself with that password, not a code."""
    token = _register_with_password(client, "strict@example.com")
    code = _fresh_code(client, issued, "strict@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": code},
        headers=_auth(token),
    )
    assert response.status_code == 403


def test_new_password_must_differ_from_the_current_one(client, magic_link_enabled, issued):
    token = _register_with_password(client, "samesame@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": FIRST_PASSPHRASE, "current_password": FIRST_PASSPHRASE},
        headers=_auth(token),
    )
    assert response.status_code == 403


def test_short_password_is_refused(client, magic_link_enabled, issued):
    token = _sign_in_by_code(client, issued, "short@example.com")
    code = _fresh_code(client, issued, "short@example.com")

    response = client.post(
        "/v1/account/password",
        json={"new_password": "short", "code": code},
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_setting_a_password_signs_out_other_devices_but_not_this_one(client, magic_link_enabled, issued):
    """A credential change is the moment to evict anyone else holding a session."""
    first = _sign_in_by_code(client, issued, "devices@example.com")
    other = client.post(
        "/v1/auth/magic-code/consume",
        json={
            "email": "devices@example.com",
            "code": _fresh_code(client, issued, "devices@example.com"),
        },
    )
    other_refresh = other.json()["refresh_token"]

    code = _fresh_code(client, issued, "devices@example.com")
    response = client.post(
        "/v1/account/password",
        json={"new_password": SECOND_PASSPHRASE, "code": code},
        headers=_auth(first),
    )
    assert response.status_code == 200, response.text
    assert response.json()["other_sessions_revoked"] >= 1

    # The device that made the change stays signed in; the other one does not.
    assert client.get("/v1/me", headers=_auth(first)).status_code == 200
    assert client.post("/v1/auth/refresh", json={"refresh_token": other_refresh}).status_code == 401


def test_setting_a_password_requires_authentication(client, require_api_auth):
    assert client.post("/v1/account/password", json={"new_password": SECOND_PASSPHRASE}).status_code == 401


def _sign_in_with_google(client: TestClient, monkeypatch, email: str) -> str:
    from thoughtpins.config import config
    from thoughtpins.oauth import OAuthIdentity

    def fake_verify(provider, token):
        return OAuthIdentity(provider="google", subject=f"sub-{email}", email=email, email_verified=True)

    monkeypatch.setattr("thoughtpins.api.verify_oauth_id_token", fake_verify)
    monkeypatch.setattr(config, "ALLOW_OAUTH_REGISTRATION", True)
    monkeypatch.setattr(type(config), "ALLOW_OAUTH_REGISTRATION", True)

    response = client.post("/v1/auth/oauth", json={"provider": "google", "id_token": "x" * 24})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
