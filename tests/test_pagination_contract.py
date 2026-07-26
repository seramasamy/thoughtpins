"""Stable, tamper-evident keyset pagination contracts."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def test_cursor_round_trip_and_tamper_detection(monkeypatch) -> None:
    from thoughtpins.config import config
    from thoughtpins.pagination import decode_cursor, encode_cursor

    monkeypatch.setattr(config, "JWT_SECRET", "cursor-test-secret")
    now = datetime(2026, 7, 13, 12, 0, 0)
    cursor = encode_cursor(sort="entries.created", direction="desc", occurred_at=now, row_id="entry-2")

    decoded = decode_cursor(cursor, sort="entries.created", direction="desc")
    assert decoded.occurred_at == now
    assert decoded.row_id == "entry-2"

    replacement = "A" if cursor[-1] != "A" else "B"
    tampered = cursor[:-1] + replacement
    try:
        decode_cursor(tampered, sort="entries.created", direction="desc")
    except ValueError as exc:
        assert "cursor" in str(exc).lower()
    else:
        raise AssertionError("A modified cursor must not validate")


def test_entries_cursor_is_stable_across_newer_insert(isolated_db) -> None:
    from thoughtpins.api import app
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        for index in range(4):
            text = f"Cursor fixture {index}"
            session.add(
                RawEntry(
                    id=f"cursor-entry-{index}",
                    user_id=user.id,
                    created_at_utc=base + timedelta(minutes=index),
                    local_date=base.date(),
                    local_time="12:00",
                    source="test",
                    raw_text=text,
                    content_hash=hash_text(text),
                    processed_status="completed",
                )
            )
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    first = client.get("/v1/entries?limit=2")
    assert first.status_code == 200
    first_body = first.json()
    assert [item["id"] for item in first_body["items"]] == ["cursor-entry-3", "cursor-entry-2"]
    assert first_body["has_next"] is True
    assert first_body["next_cursor"]

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        session.add(
            RawEntry(
                id="cursor-entry-new",
                user_id=user.id,
                created_at_utc=datetime.now(timezone.utc).replace(tzinfo=None),
                local_date=base.date(),
                local_time="13:00",
                source="test",
                raw_text="Inserted after page one",
                content_hash=hash_text("Inserted after page one"),
                processed_status="completed",
            )
        )
        session.commit()
    finally:
        session.close()

    second = client.get(f"/v1/entries?limit=2&cursor={first_body['next_cursor']}")
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == ["cursor-entry-1", "cursor-entry-0"]
    assert "cursor-entry-new" not in {item["id"] for item in second.json()["items"]}


def test_invalid_cursor_returns_consistent_error(isolated_db) -> None:
    from thoughtpins.api import app

    response = TestClient(app).get("/v1/entries?cursor=not-a-valid-cursor")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
