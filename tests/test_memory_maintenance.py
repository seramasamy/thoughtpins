from __future__ import annotations

from datetime import datetime


class FakeVectorStore:
    def __init__(self):
        self.added: list[tuple[list[str], list[str]]] = []
        self.deleted: list[str] = []
        self.reset_called = False

    def add(self, ids, texts, metadata=None):
        self.added.append((list(ids), list(texts)))

    def delete(self, ids):
        self.deleted.extend(ids)

    def reset(self):
        self.reset_called = True


def test_reindex_skips_superseded_memories(isolated_db, monkeypatch):
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.memory import reindex
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    fake = FakeVectorStore()
    monkeypatch.setattr(reindex, "get_vector_store", lambda: fake)

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="active raw",
            content_hash=hash_text("active raw"),
            processed_status="completed",
        )
        session.add(raw)
        session.flush()
        active = Memory(user_id=user.id, raw_entry_id=raw.id, memory_type="fact", text="Active memory")
        stale = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="fact",
            text="Stale memory",
            valid_to=datetime(2026, 5, 1),
        )
        session.add_all([active, stale])
        session.commit()

        stats = reindex.reindex_vectors(session=session, user_id=user.id, reset=True)

        assert stats.scanned == 1
        assert stats.indexed == 1
        assert fake.added[0][0] == [active.id]
        assert stale.id not in fake.deleted
    finally:
        session.close()


def test_correction_supersedes_old_memory_and_search_prefers_new_fact(isolated_db, monkeypatch):
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.memory import corrections
    from thoughtpins.memory import search as memory_search
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    fake = FakeVectorStore()
    monkeypatch.setattr(corrections, "_refresh_correction_vectors", lambda session, result: None)
    monkeypatch.setattr(memory_search, "get_vector_store", lambda: fake)

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Steve's kid is Jeff.",
            content_hash=hash_text("steve kid wrong"),
            processed_status="completed",
        )
        session.add(raw)
        session.flush()
        old = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="relationship",
            text="Steve's kid is Jeff.",
        )
        session.add(old)
        session.commit()

        result = corrections.store_and_apply_correction(
            session,
            "Actually Steve's kid is Geoff, not Jeff",
            user_id=user.id,
            source="test",
        )

        assert result.superseded_memory_ids == [old.id]
        session.refresh(old)
        assert old.valid_to is not None
        results = memory_search.search("who is Steve's kid?", session=session, user_id=user.id, include_private=True)
        text = "\n".join(item.text for item in results)
        assert "Geoff" in text
        assert "Steve's kid is Jeff." not in text
    finally:
        session.close()


async def test_undo_restores_superseded_memory(isolated_db, monkeypatch):
    from thoughtpins.bot import commands
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.memory import vector_store
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    fake = FakeVectorStore()
    monkeypatch.setattr(vector_store, "get_vector_store", lambda: fake)

    class FakeMessage:
        chat_id = "undo-chat"
        replies: list[str]

        def __init__(self):
            self.replies = []

        async def reply_text(self, text: str, **kwargs):
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self):
            self.message = FakeMessage()

    class FakeContext:
        args: list[str] = []

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("undo-chat", session=session)
        old_raw = RawEntry(
            user_id=user.id,
            raw_text="Steve's kid is Jeff.",
            content_hash=hash_text("undo old"),
            telegram_chat_id="undo-chat",
            processed_status="completed",
        )
        correction_raw = RawEntry(
            user_id=user.id,
            raw_text="Actually Steve's kid is Geoff, not Jeff",
            content_hash=hash_text("undo correction"),
            telegram_chat_id="undo-chat",
            processed_status="completed",
        )
        session.add_all([old_raw, correction_raw])
        session.flush()
        old_memory = Memory(
            user_id=user.id,
            raw_entry_id=old_raw.id,
            memory_type="relationship",
            text="Steve's kid is Jeff.",
            valid_to=datetime(2026, 5, 25),
        )
        session.add(old_memory)
        session.flush()
        correction_memory = Memory(
            user_id=user.id,
            raw_entry_id=correction_raw.id,
            memory_type="correction",
            text="Correction: Steve's kid is Geoff, not Jeff.",
            supersedes_memory_id=old_memory.id,
        )
        session.add(correction_memory)
        session.commit()
        old_id = old_memory.id
        correction_entry_id = correction_raw.id
    finally:
        session.close()

    update = FakeUpdate()
    await commands.cmd_undo(update, FakeContext())

    assert "Undid latest saved item" in update.message.replies[-1]
    assert "Restored 1 superseded" in update.message.replies[-1]

    session = get_session()
    try:
        restored = session.query(Memory).filter(Memory.id == old_id).one()
        assert restored.valid_to is None
        assert session.query(RawEntry).filter(RawEntry.id == correction_entry_id).first() is None
    finally:
        session.close()
