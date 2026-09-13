"""Durable derived-source processing after the original source has been saved."""

from __future__ import annotations

from sqlalchemy.orm import Session

from thoughtpins.db import DocumentSource, IngestionJob, Memory, RawEntry
from thoughtpins.users import lock_active_user_for_write


def prepare_document_enrichment(
    session: Session,
    document: DocumentSource,
    raw: RawEntry,
    text: str,
    *,
    status: str,
    defer_vector_index: bool,
) -> IngestionJob | None:
    from thoughtpins import library
    from thoughtpins.config import config

    if defer_vector_index and config.PROCESS_ENTRIES_ASYNC and status == "processed":
        return stage_document_enrichment(session, document)
    stats = library._extract_document_graph(session, document, raw, text, status=status)
    if stats:
        document.metadata_json = dict(document.metadata_json or {}) | {"graph_extraction": stats}
    library._mirror_document_to_graph_backend(session, document, raw, text, status=status)
    return None


def stage_document_enrichment(session: Session, document: DocumentSource) -> IngestionJob:
    job = IngestionJob(
        user_id=document.user_id,
        source="library_enrichment",
        raw_text="",
        entry_id=document.raw_entry_id,
        dedup_key=f"document-enrichment:{document.id}",
        status="pending",
        metadata_json={"operation": "library_enrichment", "document_id": document.id},
    )
    session.add(job)
    session.flush()
    document.metadata_json = dict(document.metadata_json or {}) | {"enrichment_job_id": job.id}
    return job


def dispatch_document_enrichment(session: Session, job: IngestionJob) -> None:
    from thoughtpins.jobs import IngestionDispatchUnavailable, dispatch_ingestion_job

    try:
        dispatch_ingestion_job(session, job, user_id=job.user_id)
    except IngestionDispatchUnavailable:
        # The source and job already committed together. The existing relay
        # recovers this retryable job; the save must not look like it was lost.
        pass


def run_document_enrichment(session: Session, *, user_id: str, document_id: str) -> dict:
    from thoughtpins import library
    from thoughtpins.crypto import maybe_decrypt_text
    from thoughtpins.memory.vector_store import get_vector_store

    lock_active_user_for_write(session, user_id)
    document = (
        session.query(DocumentSource)
        .filter(
            DocumentSource.user_id == user_id,
            DocumentSource.id == document_id,
        )
        .first()
    )
    if document is None:
        return {"type": "skipped", "entry_id": None}
    raw = session.query(RawEntry).filter(RawEntry.user_id == user_id, RawEntry.id == document.raw_entry_id).one()
    text = maybe_decrypt_text(document.raw_text)
    metadata = dict(document.metadata_json or {})
    if metadata.get("enrichment_status") != "completed":
        stats = library._extract_document_graph(session, document, raw, text, status=document.status)
        if stats and stats.get("error"):
            raise RuntimeError("Source enrichment is temporarily unavailable")
        if stats:
            metadata["graph_extraction"] = stats
        library._mirror_document_to_graph_backend(session, document, raw, text, status=document.status)
    memories = session.query(Memory).filter(Memory.user_id == user_id, Memory.raw_entry_id == raw.id).all()
    if memories:
        get_vector_store().add(
            [row.id for row in memories],
            [row.text for row in memories],
            [{"user_id": user_id} for _row in memories],
        )
    metadata["enrichment_status"] = "completed"
    document.metadata_json = metadata
    lock_active_user_for_write(session, user_id)
    # The runner commits the derived data and completed job in one transaction.
    return {"type": "library_enrichment", "entry_id": raw.id}
