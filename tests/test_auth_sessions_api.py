"""User-visible session inventory and revocation behavior."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str) -> tuple[dict, dict]:
    password = "Test-password-42!"
    registered = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 200
    first = client.post("/v1/auth/login", json={"identifier": email, "password": password})
    second = client.post("/v1/auth/login", json={"identifier": email, "password": password})
    assert first.status_code == second.status_code == 200
    return first.json(), second.json()


def test_sessions_are_scoped_labeled_and_individually_revocable(isolated_db) -> None:
    from thoughtpins.api import app

    client = TestClient(app)
    first, second = _register_and_login(client, "sessions@example.com")
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    listed = client.get("/v1/sessions", headers=second_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    current = [item for item in listed.json()["items"] if item["current"]]
    assert len(current) == 1
    first_session = next(item for item in listed.json()["items"] if not item["current"])
    assert "refresh_token" not in listed.text

    revoked = client.delete(f"/v1/sessions/{first_session['id']}", headers=second_headers)
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at_utc"]
    assert client.get("/v1/me", headers=first_headers).status_code == 401
    assert client.get("/v1/me", headers=second_headers).status_code == 200


def test_revoke_others_keeps_current_session(isolated_db) -> None:
    from thoughtpins.api import app

    client = TestClient(app)
    first, second = _register_and_login(client, "other-sessions@example.com")
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    response = client.post(
        "/v1/sessions/revoke-others",
        headers=second_headers | {"Idempotency-Key": "revoke-other-sessions-01"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "revoked", "count": 1}
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {first['access_token']}"}).status_code == 401
    assert client.get("/v1/me", headers=second_headers).status_code == 200


def test_simultaneous_refresh_rotation_has_exactly_one_winner(isolated_db, monkeypatch) -> None:
    from sqlalchemy.orm import Query

    from thoughtpins.auth import hash_password, issue_token_pair, refresh_token_pair
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    setup = get_session()
    try:
        user = register_user(
            email="refresh-race@example.com",
            password_hash=hash_password("Test-password-42!"),
            session=setup,
        )
        original = issue_token_pair(setup, user)["refresh_token"]
    finally:
        setup.close()

    barrier = Barrier(2)
    original_update = Query.update

    def synchronized_update(query, *args, **kwargs):
        barrier.wait(timeout=10)
        return original_update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "update", synchronized_update)

    def rotate():
        session = get_session()
        try:
            return refresh_token_pair(session, original)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: rotate(), range(2)))

    assert sum(outcome is not None for outcome in outcomes) == 1
