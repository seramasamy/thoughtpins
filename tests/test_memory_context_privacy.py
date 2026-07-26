from __future__ import annotations

from datetime import date

from thoughtpins.db import DocumentSource, RawEntry
from thoughtpins.memory.full_context import build_full_context, build_navigational_map
from thoughtpins.store import get_session
from thoughtpins.users import get_or_create_user_for_telegram
from thoughtpins.utils import hash_text


def test_document_context_and_counts_follow_private_scope(isolated_db) -> None:
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("context-source-privacy", session=session)
        public_entry = _entry(user.id, "public source", is_private=False)
        private_entry = _entry(user.id, "private source", is_private=True)
        session.add_all([public_entry, private_entry])
        session.flush()
        session.add_all(
            [
                _document(user.id, public_entry.id, "Public reading"),
                _document(user.id, private_entry.id, "Private reading"),
            ]
        )
        session.commit()

        standard = build_full_context(session, include_private=False, user_id=user.id)
        standard_map = build_navigational_map(session, include_private=False, user_id=user.id)
        disclosure = build_full_context(session, include_private=True, user_id=user.id)
        disclosure_map = build_navigational_map(session, include_private=True, user_id=user.id)

        assert "Public reading" in standard
        assert "Private reading" not in standard
        assert "1 sources" in standard_map
        assert "Public reading" in disclosure
        assert "Private reading" in disclosure
        assert "2 sources" in disclosure_map
    finally:
        session.close()


def _entry(user_id: str, text: str, *, is_private: bool) -> RawEntry:
    return RawEntry(
        user_id=user_id,
        raw_text=text,
        content_hash=hash_text(text),
        local_date=date(2026, 7, 21),
        local_time="12:00",
        source="app",
        is_private=is_private,
        processed_status="completed",
    )


def _document(user_id: str, raw_entry_id: str, title: str) -> DocumentSource:
    return DocumentSource(
        user_id=user_id,
        raw_entry_id=raw_entry_id,
        source_type="article",
        title=title,
        content_hash=hash_text(title),
        raw_text=f"Body for {title}",
        local_date=date(2026, 7, 21),
        status="processed",
    )
