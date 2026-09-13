from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("queue_available", [True, False])
def test_source_is_saved_before_derived_processing_and_survives_queue_failure(
    isolated_db, monkeypatch, queue_available
):
    from thoughtpins import jobs, library
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import DocumentSource, IngestionJob
    from thoughtpins.store import get_session

    monkeypatch.setattr(config, "PROCESS_ENTRIES_ASYNC", True)

    def enqueue(_job_id, user_id=None):
        if not queue_available:
            raise ConnectionError("fixture broker unavailable")

    monkeypatch.setattr(jobs, "enqueue_ingestion_job", enqueue)

    def no_inline_enrichment(*args, **kwargs):
        raise AssertionError("The save request must not wait for derived model work")

    monkeypatch.setattr(library, "_extract_document_graph", no_inline_enrichment)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", no_inline_enrichment)
    client = TestClient(app)
    response = client.post(
        "/v1/library", json={"text": "I kept a violet compass beside the orchard notebook.", "title": "Fixture"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] and body["job_id"]
    with get_session() as session:
        document = session.get(DocumentSource, body["document_id"])
        owner = document.user_id
        assert "violet compass" in document.raw_text
        job = session.get(IngestionJob, body["job_id"])
        assert job.status == ("queued" if queue_available else "retry")
        assert job.raw_text == ""  # Do not duplicate the source in the queue payload.
    monkeypatch.setattr(library, "_extract_document_graph", lambda *a, **k: {"entities_created": 0})
    monkeypatch.setattr(library, "_mirror_document_to_graph_backend", lambda *a, **k: None)
    indexed = []

    class VectorStore:
        def add(self, ids, texts, metadata):
            assert all(item["user_id"] == owner for item in metadata)
            indexed.extend(ids)

    monkeypatch.setattr("thoughtpins.memory.vector_store.get_vector_store", lambda: VectorStore())
    jobs.run_ingestion_job(body["job_id"], owner)
    jobs.run_ingestion_job(body["job_id"], owner)  # Duplicate delivery is inert.
    with get_session() as session:
        assert session.get(IngestionJob, body["job_id"]).status == "completed"
        assert session.get(DocumentSource, body["document_id"]).metadata_json["enrichment_status"] == "completed"
    assert indexed and len(indexed) == len(set(indexed))


def test_enrichment_cannot_read_another_owners_source(isolated_db, monkeypatch):
    from thoughtpins.db import DocumentSource, RawEntry
    from thoughtpins.library_enrichment import run_document_enrichment
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user
    from thoughtpins.utils import local_today

    with get_session() as session:
        owner = register_user(email="source-owner@example.invalid", session=session, bypass_system_lock=True)
        other = register_user(email="source-other@example.invalid", session=session, bypass_system_lock=True)
        raw = RawEntry(user_id=owner.id, raw_text="fixture", content_hash="fixture", local_date=local_today())
        session.add(raw)
        session.flush()
        source = DocumentSource(
            user_id=owner.id,
            raw_entry_id=raw.id,
            title="Private",
            source_type="text",
            raw_text="fixture",
            content_hash="fixture",
        )
        session.add(source)
        session.commit()
        assert run_document_enrichment(session, user_id=other.id, document_id=source.id)["type"] == "skipped"
