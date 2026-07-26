from __future__ import annotations

from datetime import datetime


def test_clear_memory_data_deletes_content_preserves_user(isolated_db, monkeypatch):
    from thoughtpins.db import Entity, Memory, RawEntry, User
    from thoughtpins.memory import reset
    from thoughtpins.memory.reset import clear_memory_data
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(reset, "_clear_directory_contents", lambda path: True)

    class FakeVectorStore:
        def reset(self) -> None:
            calls.append("reset")

    calls: list[str] = []
    monkeypatch.setattr("thoughtpins.memory.vector_store.get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr("thoughtpins.memory.vector_store.close_vector_store", lambda: calls.append("close"))

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("reset-chat", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Reset test memory.",
            content_hash=hash_text("reset test memory"),
            local_date=datetime(2026, 5, 25).date(),
            processed_status="completed",
        )
        entity = Entity(user_id=user.id, type="concept", canonical_name="Reset Concept")
        session.add_all([raw, entity])
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="observation",
                text="Reset test memory.",
                local_date=raw.local_date,
            )
        )
        session.commit()

        stats = clear_memory_data(
            session,
            dry_run=False,
            make_backup=False,
            clear_files=True,
            reset_vectors=True,
        )

        assert stats.deleted_rows["raw_entries"] == 1
        assert stats.deleted_rows["memories"] == 1
        assert stats.deleted_rows["entities"] == 1
        assert all(count == 0 for count in stats.remaining_rows.values())
        assert session.query(User).filter(User.id == user.id).count() == 1
        assert calls == ["reset", "close"]
    finally:
        session.close()


def test_public_domain_book_folder_guard(tmp_path):
    from thoughtpins.memory.reset import _delete_public_domain_test_folder

    unsafe = tmp_path / "thoughtpins_eval_corpus" / "Advisor Philosophy"
    unsafe.mkdir(parents=True)
    assert _delete_public_domain_test_folder(unsafe) is False
    assert unsafe.exists()

    safe = tmp_path / "thoughtpins_eval_corpus" / "Advisor Philosophy" / "Public Domain Test Series" / "Sherlock Holmes"
    safe.mkdir(parents=True)
    (safe / "book.txt").write_text("test", encoding="utf-8")
    assert _delete_public_domain_test_folder(safe) is True
    assert not safe.exists()
