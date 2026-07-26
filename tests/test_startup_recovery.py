from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_startup_recovery_retries_stale_entries_and_prunes_empty_entities(isolated_db, monkeypatch):
    from thoughtpins import startup_recovery
    from thoughtpins.db import Entity, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    calls: list[dict[str, object]] = []

    def fake_process(_session, text: str, **kwargs):
        calls.append({"text": text, **kwargs})

    monkeypatch.setattr(startup_recovery, "process_message", fake_process)
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        user_id = user.id
        stale = RawEntry(
            id="stale-startup-entry",
            user_id=user_id,
            created_at_utc=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
            raw_text="A stale entry safe for the test fixture.",
            content_hash=hash_text("A stale entry safe for the test fixture."),
            processed_status="processing",
        )
        orphan = Entity(
            id="old-empty-entity",
            user_id=user_id,
            type="concept",
            canonical_name="Old Empty Fixture",
            created_at_utc=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2),
        )
        session.add_all([stale, orphan])
        session.commit()
    finally:
        session.close()

    startup_recovery.recover_orphaned_entries()

    session = get_session()
    try:
        recovered = session.query(RawEntry).filter_by(id="stale-startup-entry").one()
        assert recovered.processed_status == "error"
        assert '"retries": 1' in (recovered.processing_error or "")
        assert session.query(Entity).filter_by(id="old-empty-entity").count() == 0
        assert len(calls) == 1
        assert calls[0]["user_id"] == user_id
    finally:
        session.close()
