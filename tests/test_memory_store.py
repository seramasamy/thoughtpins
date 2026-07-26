from __future__ import annotations


def test_memory_store_scopes_stats_by_user(isolated_db):
    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.memory.store import MemoryStore
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user_a = User(display_name="A", api_key="a")
        user_b = User(display_name="B", api_key="b")
        session.add_all([user_a, user_b])
        session.flush()

        entry_a = RawEntry(
            user_id=user_a.id,
            raw_text="A entry",
            content_hash=hash_text("A entry"),
            processed_status="completed",
        )
        entry_b = RawEntry(
            user_id=user_b.id,
            raw_text="B entry",
            content_hash=hash_text("B entry"),
            processed_status="completed",
        )
        session.add_all([entry_a, entry_b])
        session.flush()
        session.add_all(
            [
                Memory(user_id=user_a.id, raw_entry_id=entry_a.id, memory_type="thought", text="A memory"),
                Memory(user_id=user_b.id, raw_entry_id=entry_b.id, memory_type="thought", text="B memory"),
            ]
        )
        session.commit()

        assert MemoryStore(session, user_id=user_a.id).get_stats()["memories"] == 1
        assert MemoryStore(session, user_id=user_b.id).get_stats()["memories"] == 1
        assert MemoryStore(session).get_stats()["memories"] == 2
    finally:
        session.close()
