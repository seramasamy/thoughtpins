from __future__ import annotations

from datetime import date


def test_demo_seed_builds_weighted_week_and_cleans_up(isolated_db, monkeypatch):
    from cryptography.fernet import Fernet

    from thoughtpins.config import config
    from thoughtpins.crypto import ENCRYPTED_PREFIX, maybe_decrypt_text
    from thoughtpins.db import ChatMessage, DocumentSource, Entity, RawEntry, User
    from thoughtpins.demo import clear_demo_corpus, seed_demo_corpus
    from thoughtpins.demo.corpus import ENTITY_NAMES, MARKER, SOURCE_TITLES
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", key)
    monkeypatch.setattr(type(config), "DATA_ENCRYPTION_KEY", key)

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        stats = seed_demo_corpus(session, user.id, as_of=date(2026, 7, 13))

        assert stats["journal_entries"] == 7
        assert stats["documents"] == 3
        assert stats["document_indexing_flushed"] is True
        assert stats["rated_entries"] == 7
        assert stats["private_entries"] == 1
        assert stats["timeline_start"] == "2026-07-06"
        assert stats["timeline_end"] == "2026-07-12"

        entries = (
            session.query(RawEntry)
            .filter(RawEntry.user_id == user.id, RawEntry.source == "demo_corpus")
            .order_by(RawEntry.local_date.asc())
            .all()
        )
        assert [entry.user_importance for entry in entries] == [4, 5, 2, 3, 5, 4, 4]
        assert all(entry.contextual_salience is not None for entry in entries)
        assert all(entry.salience_model_version == "salience-v4" for entry in entries)
        assert len({entry.local_date for entry in entries}) == 7

        private_entry = next(entry for entry in entries if entry.is_private)
        assert private_entry.raw_text.startswith(ENCRYPTED_PREFIX)
        assert "nervous" in maybe_decrypt_text(private_entry.raw_text)

        documents = session.query(DocumentSource).filter(DocumentSource.user_id == user.id).all()
        assert {document.title for document in documents} == set(SOURCE_TITLES)
        assert all(MARKER not in document.title and MARKER not in document.raw_text for document in documents)
        assert {entity.canonical_name for entity in session.query(Entity).filter(Entity.user_id == user.id)} == set(
            ENTITY_NAMES
        )
        assert session.query(ChatMessage).filter(ChatMessage.user_id == user.id).count() == 2

        removed = clear_demo_corpus(session, user.id)
        assert removed > 0
        assert session.query(RawEntry).filter(RawEntry.user_id == user.id).count() == 0
        assert session.query(DocumentSource).filter(DocumentSource.user_id == user.id).count() == 0
        assert session.query(Entity).filter(Entity.user_id == user.id).count() == 0
        assert session.query(ChatMessage).filter(ChatMessage.user_id == user.id).count() == 0
        assert session.query(User).filter(User.id == user.id).one()
    finally:
        session.close()
