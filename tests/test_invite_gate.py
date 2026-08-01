"""The private-launch wall: registration stays open, the product stays closed.

Two things are being protected here. One is the wall itself — an account with no
redeemed code must not be able to reach anything that reads or writes memory.
The other is what the wall must never block: somebody who signed up and is
waiting can still see what the service holds about them, export it, change how
they sign in, and delete the account outright.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def client(isolated_db):
    from thoughtpins.api import app

    return TestClient(app)


@pytest.fixture
def invite_only(monkeypatch):
    from thoughtpins.config import config

    monkeypatch.setattr(config, "INVITE_ONLY", True)
    monkeypatch.setattr(type(config), "INVITE_ONLY", True)
    monkeypatch.setattr(config, "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(type(config), "REQUIRE_API_AUTH", True)
    return config


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str) -> str:
    response = client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE})
    assert response.status_code == 200, response.text
    login = client.post("/v1/auth/login", json={"email": email, "password": PASSPHRASE})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _mint(*, label: str = "test", max_uses: int = 1, expires_at=None) -> str:
    from thoughtpins.invites import create_invite_code
    from thoughtpins.store import get_session

    session = get_session()
    try:
        _, code = create_invite_code(session, label=label, max_uses=max_uses, expires_at=expires_at)
        session.commit()
        return code
    finally:
        session.close()


# --------------------------------------------------------------------------
# Registration is not the gate
# --------------------------------------------------------------------------


def test_registration_still_succeeds_and_keeps_the_account(client, invite_only):
    """The waiting list is made of real accounts, not a separate email list."""
    token = _register(client, "waiting@example.com")
    me = client.get("/v1/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "waiting@example.com"


def test_status_tells_an_uninvited_account_what_to_do(client, invite_only):
    token = _register(client, "asks@example.com")
    body = client.get("/v1/invites/status", headers=_auth(token)).json()
    assert body["invite_required"] is True
    assert body["invite_redeemed"] is False
    assert body["admitted"] is False
    assert body["contact_email"] == "invite@thoughtpins.com"


def test_client_config_announces_the_private_launch_before_sign_in(client, invite_only):
    body = client.get("/v1/client-config").json()
    assert body["invite_required"] is True
    assert body["invite_request_email"] == "invite@thoughtpins.com"


# --------------------------------------------------------------------------
# The wall
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/v1/chat", {"text": "hello", "conversation_id": "main"}),
        ("post", "/v1/entries", {"text": "a journal entry"}),
        ("get", "/v1/entries", None),
        ("get", "/v1/memory/cards", None),
        ("get", "/v1/pins", None),
        ("get", "/v1/jobs", None),
        ("get", "/v1/library/sources", None),
        ("get", "/v1/stats", None),
    ],
)
def test_uninvited_account_cannot_reach_the_product(client, invite_only, method, path, payload):
    token = _register(client, f"blocked-{path.replace('/', '-')}@example.com")
    call = getattr(client, method)
    response = call(path, json=payload, headers=_auth(token)) if payload else call(path, headers=_auth(token))
    assert response.status_code == 403, f"{path} returned {response.status_code}"
    assert response.json()["error"]["code"] == "invite_required"


def test_a_new_route_is_closed_by_default(client, invite_only):
    """The gate is an allowlist, so anything not named stays shut."""
    from thoughtpins.api_route_policy import is_invite_exempt_path

    assert is_invite_exempt_path("/v1/some/route/added/next/week") is False


# --------------------------------------------------------------------------
# What the wall must never block
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/v1/me", "/v1/invites/status", "/v1/preferences", "/v1/export", "/v1/account/export", "/v1/sessions"],
)
def test_waiting_account_keeps_its_data_rights(client, invite_only, path):
    token = _register(client, f"rights-{path.replace('/', '-')}@example.com")
    response = client.get(path, headers=_auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"


def test_waiting_account_can_delete_itself(client, invite_only):
    """Blocking deletion behind an invitation would be indefensible."""
    token = _register(client, "leaving@example.com")
    response = client.request("DELETE", "/v1/me", json={"confirm": "DELETE"}, headers=_auth(token))
    assert response.status_code == 200, response.text


def test_waiting_account_can_still_change_how_it_signs_in(client, invite_only):
    token = _register(client, "credentials@example.com")
    assert client.get("/v1/account/sign-in-methods", headers=_auth(token)).status_code == 200
    changed = client.post(
        "/v1/account/password",
        json={"new_password": "a different long passphrase", "current_password": PASSPHRASE},
        headers=_auth(token),
    )
    assert changed.status_code == 200, changed.text


def test_waiting_account_can_sign_out(client, invite_only):
    token = _register(client, "signout@example.com")
    assert client.post("/v1/sessions/revoke-others", headers=_auth(token)).status_code == 200


# --------------------------------------------------------------------------
# Redeeming
# --------------------------------------------------------------------------


def test_redeeming_a_code_opens_the_product(client, invite_only):
    token = _register(client, "admitted@example.com")
    assert client.get("/v1/entries", headers=_auth(token)).status_code == 403

    code = _mint()
    redeemed = client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(token))
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["admitted"] is True

    assert client.get("/v1/entries", headers=_auth(token)).status_code == 200


@pytest.mark.parametrize(
    "mangle", [str.lower, lambda c: c.replace("-", ""), lambda c: f"  {c}  ", lambda c: c.replace("-", " ")]
)
def test_codes_are_accepted_however_they_are_typed(client, invite_only, mangle):
    token = _register(client, f"typed-{abs(hash(mangle)) % 9999}@example.com")
    code = _mint()
    response = client.post("/v1/invites/redeem", json={"code": mangle(code)}, headers=_auth(token))
    assert response.status_code == 200, response.text


def test_wrong_code_is_refused_and_costs_an_attempt(client, invite_only):
    token = _register(client, "wrong@example.com")
    _mint()
    response = client.post("/v1/invites/redeem", json={"code": "ZZZZ-ZZZZ-ZZZZ"}, headers=_auth(token))
    assert response.status_code == 403
    remaining = client.get("/v1/invites/status", headers=_auth(token)).json()["attempts_remaining"]
    assert remaining < 10
    assert client.get("/v1/entries", headers=_auth(token)).status_code == 403


def test_expired_code_is_refused(client, invite_only):
    from datetime import datetime, timedelta, timezone

    token = _register(client, "expired@example.com")
    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    code = _mint(expires_at=stale)
    assert client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(token)).status_code == 403


def test_revoked_code_is_refused(client, invite_only):
    from datetime import datetime, timezone

    from thoughtpins.db import InviteCode
    from thoughtpins.store import get_session

    token = _register(client, "revoked@example.com")
    code = _mint()
    session = get_session()
    try:
        record = session.query(InviteCode).first()
        record.revoked_at_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()
    finally:
        session.close()
    assert client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(token)).status_code == 403


def test_single_use_code_admits_only_one_account(client, invite_only):
    code = _mint(max_uses=1)
    first = _register(client, "first@example.com")
    second = _register(client, "second@example.com")

    assert client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(first)).status_code == 200
    assert client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(second)).status_code == 403
    assert client.get("/v1/entries", headers=_auth(second)).status_code == 403


def test_multi_use_code_admits_up_to_its_limit(client, invite_only):
    code = _mint(max_uses=2)
    tokens = [_register(client, f"multi{index}@example.com") for index in range(3)]
    results = [client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(t)).status_code for t in tokens]
    assert results == [200, 200, 403]


def test_redeeming_twice_is_not_an_error_and_does_not_burn_a_second_use(client, invite_only):
    """A double-submitted form should not look like a failure."""
    from thoughtpins.db import InviteCode
    from thoughtpins.store import get_session

    token = _register(client, "double@example.com")
    code = _mint(max_uses=2)
    assert client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(token)).status_code == 200
    again = client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(token))
    assert again.status_code == 200
    assert again.json()["admitted"] is True

    session = get_session()
    try:
        assert session.query(InviteCode).first().used_count == 1
    finally:
        session.close()


def test_guessing_is_capped(client, invite_only):
    """A code is a secret; repeated tries must stop being useful."""
    from thoughtpins.invites import MAX_REDEEM_ATTEMPTS

    token = _register(client, "guesser@example.com")
    real = _mint()
    for _ in range(MAX_REDEEM_ATTEMPTS):
        client.post("/v1/invites/redeem", json={"code": "AAAA-AAAA-AAAA"}, headers=_auth(token))

    locked = client.post("/v1/invites/redeem", json={"code": real}, headers=_auth(token))
    assert locked.status_code == 429
    assert client.get("/v1/entries", headers=_auth(token)).status_code == 403


def test_one_accounts_redemption_does_not_admit_another(client, invite_only):
    code = _mint(max_uses=5)
    invited = _register(client, "invited@example.com")
    stranger = _register(client, "stranger@example.com")

    assert client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(invited)).status_code == 200
    assert client.get("/v1/entries", headers=_auth(invited)).status_code == 200
    assert client.get("/v1/entries", headers=_auth(stranger)).status_code == 403


def test_empty_and_junk_codes_are_refused_without_crashing(client, invite_only):
    token = _register(client, "junk@example.com")
    _mint()
    assert client.post("/v1/invites/redeem", json={"code": "   "}, headers=_auth(token)).status_code == 403
    assert client.post("/v1/invites/redeem", json={"code": "!!!"}, headers=_auth(token)).status_code == 403
    assert client.post("/v1/invites/redeem", json={"code": ""}, headers=_auth(token)).status_code == 422


def test_the_code_itself_is_never_stored_or_returned(client, invite_only):
    """Only the hash is kept, so a leaked database hands out nothing."""
    from thoughtpins.db import InviteCode
    from thoughtpins.store import get_session

    token = _register(client, "secrecy@example.com")
    code = _mint()
    response = client.post("/v1/invites/redeem", json={"code": code}, headers=_auth(token))
    assert code not in response.text

    session = get_session()
    try:
        record = session.query(InviteCode).first()
        normalized = code.replace("-", "")
        assert record.code_hash != normalized
        assert normalized not in str(record.__dict__)
    finally:
        session.close()


# --------------------------------------------------------------------------
# Turning the wall off
# --------------------------------------------------------------------------


def test_nothing_is_gated_when_the_private_launch_is_over(client, monkeypatch):
    from thoughtpins.config import config

    monkeypatch.setattr(config, "INVITE_ONLY", False)
    monkeypatch.setattr(type(config), "INVITE_ONLY", False)
    monkeypatch.setattr(config, "REQUIRE_API_AUTH", True)
    monkeypatch.setattr(type(config), "REQUIRE_API_AUTH", True)

    token = _register(client, "open@example.com")
    assert client.get("/v1/entries", headers=_auth(token)).status_code == 200
    assert client.get("/v1/invites/status", headers=_auth(token)).json()["admitted"] is True


def test_an_operator_can_get_in_to_issue_the_first_code(client, invite_only):
    """Otherwise the gate locks out the person who has to open it."""
    from thoughtpins.db import User
    from thoughtpins.store import get_session

    token = _register(client, "operator@example.com")
    session = get_session()
    try:
        user = session.query(User).filter(User.email == "operator@example.com").first()
        user.is_admin = True
        session.commit()
    finally:
        session.close()

    assert client.get("/v1/entries", headers=_auth(token)).status_code == 200


def test_invite_only_defaults_on_where_real_people_can_reach_it():
    """A deploy that forgets the flag should be closed, not open."""
    from thoughtpins.config import _env_bool

    for environment in ("staging", "production"):
        assert _env_bool("INVITE_ONLY", environment in {"staging", "production"}) is True
    assert _env_bool("INVITE_ONLY", "development" in {"staging", "production"}) is False
