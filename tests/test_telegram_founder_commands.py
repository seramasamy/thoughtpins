from __future__ import annotations

from datetime import datetime


class FakeMessage:
    def __init__(self, chat_id: str = "founder-chat"):
        self.chat_id = chat_id
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, chat_id: str = "founder-chat"):
        self.message = FakeMessage(chat_id)


class FakeContext:
    def __init__(self, args: list[str] | None = None):
        self.args = args or []


async def test_founder_memory_review_rename_and_forget(isolated_db, monkeypatch):
    from thoughtpins.bot import commands
    from thoughtpins.db import Entity, Memory, RawEntry, Relationship
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(commands, "_delete_memory_vector", lambda memory_id: None)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("founder-chat", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Mya talked about the reliability roadmap at Blue Bottle.",
            content_hash=hash_text("founder command raw"),
            telegram_chat_id="founder-chat",
            processed_status="completed",
            local_date=datetime(2026, 5, 24).date(),
            local_time="12:00",
        )
        person = Entity(user_id=user.id, type="person", canonical_name="Mya")
        place = Entity(user_id=user.id, type="place", canonical_name="Blue Bottle")
        orphan = Entity(user_id=user.id, type="concept", canonical_name="Unused Concept")
        session.add_all([raw, person, place, orphan])
        session.flush()
        memory = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="conversation",
            subject_entity_id=person.id,
            object_entity_id=place.id,
            text="Mya talked about the reliability roadmap at Blue Bottle.",
            local_date=datetime(2026, 5, 24).date(),
        )
        session.add(memory)
        session.flush()
        session.add(
            Relationship(
                user_id=user.id,
                source_entity_id=person.id,
                target_entity_id=place.id,
                relation_type="met_at",
                raw_entry_id=raw.id,
                memory_id=memory.id,
            )
        )
        memory_id = memory.id
        session.commit()
    finally:
        session.close()

    update = FakeUpdate()
    await commands.cmd_people(update, FakeContext())
    assert "Mya" in update.message.replies[-1]
    assert "memories=1" in update.message.replies[-1]

    update = FakeUpdate()
    await commands.cmd_forget(update, FakeContext(["entity", "Mya"]))
    assert "Refusing to delete" in update.message.replies[-1]

    update = FakeUpdate()
    await commands.cmd_rename(update, FakeContext(["Mya", "->", "Maya"]))
    assert "Renamed 'Mya' -> 'Maya'" in update.message.replies[-1]

    session = get_session()
    try:
        renamed = session.query(Entity).filter(Entity.canonical_name == "Maya").one()
        assert "Mya" in (renamed.aliases_json or [])
    finally:
        session.close()

    update = FakeUpdate()
    await commands.cmd_forget(update, FakeContext(["memory", memory_id[:8]]))
    assert "Forgot memory" in update.message.replies[-1]

    session = get_session()
    try:
        assert session.query(Memory).filter(Memory.id == memory_id).first() is None
        assert session.query(Relationship).filter(Relationship.memory_id == memory_id).count() == 0
    finally:
        session.close()

    update = FakeUpdate()
    await commands.cmd_forget(update, FakeContext(["entity", "Unused Concept"]))
    assert "Forgot orphan entity" in update.message.replies[-1]


def test_context_diagnostics_excludes_memory_text_and_private_context(isolated_db, monkeypatch):
    from thoughtpins.bot import commands
    from thoughtpins.config import config
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(config, "MEMORY_CONTEXT_MODE", "smart")
    monkeypatch.setattr(type(config), "MEMORY_CONTEXT_MODE", "smart")
    monkeypatch.setattr(config, "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    monkeypatch.setattr(type(config), "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)

    private_text = "Private seed phrase should never appear in public context."
    public_text = "Maya said reliability should come before UI polish."

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("context-chat", session=session)
        public_raw = RawEntry(
            user_id=user.id,
            raw_text=public_text,
            content_hash=hash_text("diag public"),
            telegram_chat_id="context-chat",
            processed_status="completed",
            is_private=False,
            local_date=datetime(2026, 5, 23).date(),
            local_time="09:00",
        )
        private_raw = RawEntry(
            user_id=user.id,
            raw_text=private_text,
            content_hash=hash_text("diag private"),
            telegram_chat_id="context-chat",
            processed_status="completed",
            is_private=True,
            local_date=datetime(2026, 5, 24).date(),
            local_time="10:00",
        )
        session.add_all([public_raw, private_raw])
        session.flush()
        session.add_all(
            [
                Memory(
                    user_id=user.id,
                    raw_entry_id=public_raw.id,
                    memory_type="decision",
                    text=public_text,
                    local_date=datetime(2026, 5, 23).date(),
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=private_raw.id,
                    memory_type="secret",
                    text=private_text,
                    local_date=datetime(2026, 5, 24).date(),
                ),
            ]
        )
        session.commit()

        context_text = commands.build_memory_context_package(
            "what did Maya say about reliability?",
            session,
            chat_id="context-chat",
            include_private=False,
            user_id=user.id,
            include_vault=False,
        )
        diagnostics = commands.describe_memory_context_package(
            "what did Maya say about reliability?",
            session,
            chat_id="context-chat",
            include_private=False,
            user_id=user.id,
        )
        diagnostic_reply = commands._format_context_diagnostics(diagnostics)

        assert public_text in context_text
        assert private_text not in context_text
        assert public_text not in diagnostic_reply
        assert private_text not in diagnostic_reply
        assert "Sections attached" in diagnostic_reply
    finally:
        session.close()
