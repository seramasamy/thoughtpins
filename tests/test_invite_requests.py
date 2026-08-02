"""Asking to be let in must never become a way to flood the operator's inbox.

The queue is the record; email is only a notification about it. So the tests
that matter are the ones proving the amount of mail does not scale with the
number of requests, and that a failure to notify never loses a request.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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

    for key, value in (
        ("INVITE_ONLY", True),
        ("REQUIRE_API_AUTH", True),
        ("INVITE_NOTIFY_EMAIL", "operator@example.com"),
        ("EMAIL_PROVIDER", "resend"),
        ("RESEND_API_KEY", "test-key"),
        ("EMAIL_FROM_ADDRESS", "no-reply@example.com"),
    ):
        monkeypatch.setattr(config, key, value)
        monkeypatch.setattr(type(config), key, value)
    return config


@pytest.fixture
def sent(monkeypatch) -> list[dict]:
    """Capture outbound mail instead of delivering it."""
    captured: list[dict] = []

    def capture(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr("thoughtpins.invite_requests.send_email", capture)
    return captured


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, email: str) -> str:
    assert client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE}).status_code == 200
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSPHRASE})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _ask(client: TestClient, token: str, note: str = "") -> int:
    return client.post("/v1/invites/request", json={"note": note or None}, headers=_auth(token)).status_code


# --------------------------------------------------------------------------
# Joining the queue
# --------------------------------------------------------------------------


def test_a_waiting_account_can_ask_without_leaving_the_page(client, invite_only, sent):
    token = _register(client, "asker@example.com")
    response = client.post("/v1/invites/request", json={"note": "I take a lot of notes."}, headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "received"
    assert response.json()["note"] == "I take a lot of notes."


def test_the_note_is_optional(client, invite_only, sent):
    token = _register(client, "quiet@example.com")
    response = client.post("/v1/invites/request", json={}, headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["note"] is None


def test_asking_repeatedly_does_not_pile_up_rows(client, invite_only, sent):
    """Asking twice is the same ask, not a second place in the queue."""
    from thoughtpins.db import InviteRequest
    from thoughtpins.store import get_session

    token = _register(client, "repeat@example.com")
    for index in range(6):
        assert _ask(client, token, f"attempt {index}") == 200

    session = get_session()
    try:
        assert session.query(InviteRequest).count() == 1
        assert session.query(InviteRequest).first().note == "attempt 5"
    finally:
        session.close()


def test_asking_does_not_open_the_product(client, invite_only, sent):
    token = _register(client, "stillwaiting@example.com")
    assert _ask(client, token) == 200
    assert client.get("/v1/entries", headers=_auth(token)).status_code == 403


# --------------------------------------------------------------------------
# The inbox protection
# --------------------------------------------------------------------------


def test_many_requests_produce_one_email(client, invite_only, sent):
    """The whole point: mail volume must not track request volume."""
    for index in range(25):
        token = _register(client, f"crowd{index}@example.com")
        _ask(client, token, "please")

    assert len(sent) == 1, f"expected a single digest, got {len(sent)}"
    assert sent[0]["to"] == "operator@example.com"


def test_the_subject_is_prefixed_so_it_can_be_filtered(client, invite_only, sent):
    token = _register(client, "subject@example.com")
    _ask(client, token)
    assert sent[0]["subject"].startswith("[THOUGHTPINS]")


def test_a_second_digest_waits_for_the_interval(client, invite_only, sent):
    from thoughtpins.config import config

    token = _register(client, "first@example.com")
    _ask(client, token)
    assert len(sent) == 1

    second = _register(client, "second@example.com")
    _ask(client, second)
    assert len(sent) == 1, "a new request inside the interval must not send again"

    # Once the interval has passed, the next request may notify.
    _rewind_notifications(minutes=config.INVITE_DIGEST_MIN_INTERVAL_MINUTES + 10)
    third = _register(client, "third@example.com")
    _ask(client, third)
    assert len(sent) == 2


def test_the_daily_ceiling_holds_even_if_the_interval_is_misconfigured(client, invite_only, sent, monkeypatch):
    """Two independent limits, so one being wrong cannot open the floodgate."""
    from thoughtpins.config import config

    monkeypatch.setattr(config, "INVITE_DIGEST_MIN_INTERVAL_MINUTES", 1)
    monkeypatch.setattr(type(config), "INVITE_DIGEST_MIN_INTERVAL_MINUTES", 1)

    for index in range(8):
        token = _register(client, f"ceiling{index}@example.com")
        _ask(client, token)
        _rewind_notifications(minutes=5)

    assert len(sent) <= config.INVITE_DIGEST_MAX_PER_DAY


def test_nothing_is_emailed_when_no_recipient_is_configured(client, invite_only, sent, monkeypatch):
    from thoughtpins.config import config

    monkeypatch.setattr(config, "INVITE_NOTIFY_EMAIL", "")
    monkeypatch.setattr(type(config), "INVITE_NOTIFY_EMAIL", "")

    token = _register(client, "norecipient@example.com")
    assert _ask(client, token) == 200
    assert sent == []


def test_a_failed_notification_never_loses_the_request(client, invite_only, monkeypatch):
    """The queue is the record. Delivery is best effort."""
    from thoughtpins.db import InviteRequest
    from thoughtpins.email_delivery import EmailDeliveryError
    from thoughtpins.store import get_session

    def explode(**kwargs):
        raise EmailDeliveryError("provider is down")

    monkeypatch.setattr("thoughtpins.invite_requests.send_email", explode)

    token = _register(client, "resilient@example.com")
    assert _ask(client, token, "still counts") == 200

    session = get_session()
    try:
        record = session.query(InviteRequest).first()
        assert record is not None
        assert record.note == "still counts"
        # Left unnotified, so the next digest picks it up.
        assert record.notified_at_utc is None
    finally:
        session.close()


def test_the_digest_does_not_carry_addresses(client, invite_only, sent):
    """Look them up in the queue instead; the email is only a nudge."""
    token = _register(client, "private-address@example.com")
    _ask(client, token, "hello")
    body = sent[0]["text"] + sent[0]["html"]
    assert "private-address@example.com" not in body


# --------------------------------------------------------------------------
# Reading the queue
# --------------------------------------------------------------------------


def test_the_operator_can_read_the_queue(client, invite_only, sent):
    from thoughtpins.db import User
    from thoughtpins.store import get_session

    waiting = _register(client, "inqueue@example.com")
    _ask(client, waiting, "a good reason")

    operator = _register(client, "operator-account@example.com")
    session = get_session()
    try:
        user = session.query(User).filter(User.email == "operator-account@example.com").first()
        user.is_admin = True
        session.commit()
    finally:
        session.close()

    response = client.get("/v1/admin/invite-requests", headers=_auth(operator))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pending"] >= 1
    match = [row for row in body["requests"] if row["email"] == "inqueue@example.com"]
    assert match and match[0]["note"] == "a good reason"


def test_the_queue_is_not_readable_by_an_ordinary_account(client, invite_only, sent):
    token = _register(client, "nosy@example.com")
    _ask(client, token)
    assert client.get("/v1/admin/invite-requests", headers=_auth(token)).status_code == 403


def test_requesting_requires_being_signed_in(client, invite_only):
    assert client.post("/v1/invites/request", json={"note": "hi"}).status_code == 401


def _rewind_notifications(*, minutes: int) -> None:
    """Age the operator ledger so the throttle sees time having passed.

    The throttle reads operator_notifications, not the requests themselves:
    request rows are tenant scoped and cannot be counted across accounts from
    inside a request.
    """
    from thoughtpins.db import InviteRequest, OperatorNotification
    from thoughtpins.store import get_session

    session = get_session()
    try:
        shift = timedelta(minutes=minutes)
        for record in session.query(OperatorNotification).all():
            record.sent_at_utc = record.sent_at_utc - shift
        for record in session.query(InviteRequest).filter(InviteRequest.notified_at_utc.isnot(None)).all():
            record.notified_at_utc = record.notified_at_utc - shift
        session.commit()
    finally:
        session.close()


def test_note_length_is_bounded(client, invite_only, sent):
    token = _register(client, "verbose@example.com")
    response = client.post("/v1/invites/request", json={"note": "x" * 5000}, headers=_auth(token))
    assert response.status_code == 422


def test_utcnow_is_naive_like_the_rest_of_the_schema():
    from thoughtpins.invite_requests import _utcnow

    assert _utcnow().tzinfo is None
    assert abs((_utcnow() - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) < 5


def test_deleting_an_account_takes_its_request_with_it(client, invite_only, sent):
    """The row carries a foreign key to users and is that person's data."""
    from thoughtpins.db import InviteRequest
    from thoughtpins.store import get_session

    token = _register(client, "departing@example.com")
    assert _ask(client, token, "please let me in") == 200

    session = get_session()
    try:
        assert session.query(InviteRequest).count() == 1
    finally:
        session.close()

    assert client.request("DELETE", "/v1/me", json={"confirm": "DELETE"}, headers=_auth(token)).status_code == 200

    session = get_session()
    try:
        assert session.query(InviteRequest).count() == 0
    finally:
        session.close()


def test_the_throttle_does_not_depend_on_reading_other_tenants_rows(client, invite_only, sent):
    """The bug this guards against only appeared in production.

    The RLS tenant is applied when a transaction begins, so a nested tenant
    context inside a request never reaches PostgreSQL. Counting past digests by
    scanning invite_requests therefore saw only the requesting account, every
    newcomer looked like the first, and each arrival sent another email. The
    throttle now reads a non-tenant ledger, which cannot be scoped away.
    """
    from thoughtpins.db import InviteRequest, OperatorNotification
    from thoughtpins.store import get_session

    for index in range(5):
        token = _register(client, f"tenantwalk{index}@example.com")
        _ask(client, token, "please")

    assert len(sent) == 1

    session = get_session()
    try:
        # One ledger row per email, regardless of how many accounts asked.
        assert session.query(OperatorNotification).count() == 1
        assert session.query(InviteRequest).count() == 5
    finally:
        session.close()


def test_the_operator_queue_reads_every_tenant(client, invite_only, sent):
    """Reading the queue from inside a request must not return only the reader."""
    from thoughtpins.db import User
    from thoughtpins.store import get_session

    for index in range(3):
        token = _register(client, f"queued{index}@example.com")
        _ask(client, token, f"reason {index}")

    operator = _register(client, "reader@example.com")
    session = get_session()
    try:
        user = session.query(User).filter(User.email == "reader@example.com").first()
        user.is_admin = True
        session.commit()
    finally:
        session.close()

    body = client.get("/v1/admin/invite-requests", headers=_auth(operator)).json()
    assert body["pending"] == 3, body
