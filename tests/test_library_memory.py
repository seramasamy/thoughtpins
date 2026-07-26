from __future__ import annotations

from datetime import datetime, timedelta


def test_classifier_distinguishes_chat_journal_and_sources():
    from thoughtpins.ingestion.classify import classify_message

    assert classify_message("whats up bro")["type"] == "conversation"
    assert classify_message("today I worked on the exact recall router")["type"] == "journal_entry"
    assert classify_message("read: https://example.com/article")["type"] == "document_link"
    assert classify_message("I think memory is mostly attention")["type"] == "ambiguous"
    assert classify_message("today I talked with Priya about recall quality, what do you think?")["type"] == "mixed"


def test_library_ingest_creates_separate_source_memories_and_search(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import DocumentChunk, DocumentSource, Memory, RawEntry
    from thoughtpins.library import ingest_document_text
    from thoughtpins.memory.search import search
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    text = (
        "The Orchard Protocol article argues that durable personal AI needs exact provenance. "
        "It says obscure details like the amber notebook test should remain retrievable. "
        "The piece concludes that reading memory and journal memory need separate labels."
    )

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("library-chat", session=session)
        result = ingest_document_text(
            session,
            text,
            user_id=user.id,
            source_type="article",
            title="Orchard Protocol Notes",
        )

        assert result.status == "processed"
        assert result.chunks == 1
        assert result.memories == 3
        assert session.query(DocumentSource).filter(DocumentSource.user_id == user.id).count() == 1
        assert session.query(DocumentChunk).filter(DocumentChunk.user_id == user.id).count() == 1
        raw = session.query(RawEntry).filter(RawEntry.id == result.raw_entry_id).one()
        assert raw.source == "library_doc"

        source_memories = (
            session.query(Memory)
            .filter(
                Memory.user_id == user.id,
                Memory.source_provenance == f"document:{result.document_id}",
            )
            .all()
        )
        assert {memory.memory_type for memory in source_memories} == {
            "source_summary",
            "source_characteristics",
            "source_excerpt",
        }

        results = search("amber notebook provenance", session=session, user_id=user.id, limit=5)
        assert results
        assert any(result.source_kind == "document" for result in results)
        assert any("amber notebook" in result.evidence_text.lower() for result in results)
    finally:
        session.close()


def test_smart_context_finds_old_obscure_document_detail(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.bot.commands import build_memory_context_package
    from thoughtpins.config import config
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.library import ingest_document_text
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(config, "MEMORY_CONTEXT_MODE", "smart")
    monkeypatch.setattr(type(config), "MEMORY_CONTEXT_MODE", "smart")
    monkeypatch.setattr(config, "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    monkeypatch.setattr(type(config), "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("library-context", session=session)
        for index in range(340):
            raw = RawEntry(
                user_id=user.id,
                raw_text=f"Routine filler memory {index}",
                content_hash=hash_text(f"routine filler {index}"),
                telegram_chat_id="library-context",
                processed_status="completed",
                local_date=(datetime(2025, 1, 1) + timedelta(days=index)).date(),
                local_time="09:00",
            )
            session.add(raw)
            session.flush()
            session.add(
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="observation",
                    text=f"Routine filler memory {index}",
                    local_date=raw.local_date,
                    created_at_utc=raw.created_at_utc,
                )
            )
        session.commit()

        ingest_document_text(
            session,
            "The old paper mentioned the violet keystone detail as the decisive recall test.",
            user_id=user.id,
            title="Old Recall Paper",
        )

        context = build_memory_context_package(
            "what was the violet keystone detail?",
            session,
            chat_id="library-context",
            include_private=False,
            user_id=user.id,
            include_vault=False,
            max_chars=60_000,
        )

        assert "QUERY-RELEVANT MEMORIES AND SOURCES" in context
        assert "violet keystone detail" in context
        assert "Old Recall Paper" in context
    finally:
        session.close()


def test_library_api_roundtrip(isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins import library
    from thoughtpins.api import app

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    client = TestClient(app)

    create = client.post(
        "/v1/library",
        json={
            "title": "Reading Memory API Test",
            "source_type": "article",
            "text": "This source says the copper lighthouse marker should be recalled later.",
        },
    )
    assert create.status_code == 200
    body = create.json()
    assert body["status"] == "processed"
    assert body["memories"] >= 2

    listing = client.get("/v1/library")
    assert listing.status_code == 200
    assert listing.json()[0]["title"] == "Reading Memory API Test"

    detail = client.get(f"/v1/library/{body['document_id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert "copper lighthouse" in detail_body["summary"]
    assert "raw_text" not in detail_body
    assert "chunks" in detail_body
    assert isinstance(detail_body["topics"], list)
    assert isinstance(detail_body["key_concepts"], list)


def test_library_api_defers_vector_indexing_for_request_latency(isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins import library
    from thoughtpins.api import app

    queued: list[str] = []

    def fail_inline_index(memories):
        raise AssertionError("API request should not wait on vector indexing")

    def fake_schedule(memories):
        queued.extend(memory.id for memory in memories)

    monkeypatch.setattr(library, "_index_document_memories", fail_inline_index)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", fake_schedule)

    response = TestClient(app).post(
        "/v1/library",
        json={
            "title": "Deferred Index API Test",
            "source_type": "article",
            "text": "This source says the brass comet marker should save before embeddings finish.",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert len(queued) >= 2
