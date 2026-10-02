"""Scanned-PDF OCR as a durable worker job, not inside the upload request.

The upload request reads only a PDF's embedded text. When a page needs OCR, it
keeps the original (as every upload does) and commits a ``pdf_ocr`` job with
it. A library upload also gets a pending source at once, so every client still
receives its document id; a journal upload gets the job, as asynchronous
journal saves already do. The worker reads the stored original and extracts the
whole PDF again under the worker limits, a longer budget and every page, with
Celery's hard time limit behind them. It then finishes the source, or saves the
journal entry. A PDF that yields no text, or outlives the time limit twice,
ends readable as such ("needs_text"), never stuck in processing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.db import DocumentChunk, DocumentSource, IngestionJob, RawEntry
from thoughtpins.library_text import chunk_text, clean_text, raw_entry_text, rough_token_count, summarize_text
from thoughtpins.media.extraction_types import MediaExtraction
from thoughtpins.media.pdf import unreadable_pdf_message
from thoughtpins.reading_analysis import reading_analysis_metadata
from thoughtpins.users import lock_active_user_for_write
from thoughtpins.utils import hash_text, local_today

OPERATION = "pdf_ocr"
PENDING_STATUS = "processing"
UNREADABLE_STATUS = "needs_text"
# Attempts before a PDF is finished as unreadable instead of retried. Each
# attempt that dies is one Celery's hard time limit stopped, and the next would too.
MAX_ATTEMPTS = 2
_PENDING_SUMMARY = "Scanned pages are being read with OCR."
_TOO_LONG = "This PDF took too long to read. Split it into smaller files, or paste the text."


@dataclass(frozen=True)
class StagedOcr:
    job_id: str | None
    status: str = "queued"
    document_id: str | None = None
    raw_entry_id: str | None = None
    title: str | None = None
    duplicate: bool = False


def upload_content_hash(content: bytes) -> str:
    """Identify a pending source by its original's bytes.

    It has no text to hash yet, and the hash stays after OCR, so uploading the
    same scan again finds this source instead of reading it twice.
    """
    return hash_text("upload-bytes\n" + hashlib.sha256(content).hexdigest())


def stage_library_ocr(
    session: Session,
    *,
    user_id: str,
    content: bytes,
    attachment: str,
    caption: str,
    title: str,
    source_type: str,
    upload_metadata: dict[str, Any],
) -> StagedOcr:
    """Commit a pending library source and its OCR job together, then dispatch the job."""
    lock_active_user_for_write(session, user_id)
    content_hash = upload_content_hash(content)
    existing = (
        session.query(DocumentSource)
        .filter(DocumentSource.user_id == user_id, DocumentSource.content_hash == content_hash)
        .first()
    )
    if existing is not None:
        pending = existing.status == PENDING_STATUS
        upload = (existing.metadata_json or {}).get("upload") or {}
        return StagedOcr(
            job_id=upload.get("ocr_job_id") if pending else None,
            status="queued" if pending else existing.status,
            document_id=existing.id,
            raw_entry_id=existing.raw_entry_id,
            title=existing.title,
            duplicate=True,
        )
    now, today = _utcnow(), local_today()
    raw = RawEntry(
        user_id=user_id,
        created_at_utc=now,
        local_date=today,
        local_time=now.strftime("%H:%M"),
        source="library_doc",
        raw_text=raw_entry_text(title, _PENDING_SUMMARY, None, PENDING_STATUS, None),
        content_hash=content_hash,
        is_private=False,
        sensitivity="personal",
        processed_status=PENDING_STATUS,
    )
    session.add(raw)
    session.flush()
    document = DocumentSource(
        user_id=user_id,
        raw_entry_id=raw.id,
        source_type=source_type,
        title=title,
        access_method="user_upload",
        rights_basis="user_provided",
        fetch_status=PENDING_STATUS,
        content_hash=content_hash,
        raw_text="",
        summary=_PENDING_SUMMARY,
        status=PENDING_STATUS,
        sensitivity="personal",
        created_at_utc=now,
        local_date=today,
        metadata_json={"upload": upload_metadata},
    )
    session.add(document)
    session.flush()
    # No entry_id until the job finishes: deleting the pending source must not
    # depend on how a database treats a job that still points at its entry.
    job = _stage_job(
        session,
        user_id=user_id,
        metadata={"destination": "library", "document_id": document.id, "attachment": attachment, "caption": caption},
    )
    document.metadata_json = {"upload": upload_metadata | {"ocr_job_id": job.id}}
    lock_active_user_for_write(session, user_id)
    session.commit()
    _dispatch(session, job)
    return StagedOcr(job_id=job.id, document_id=document.id, raw_entry_id=raw.id, title=title)


def stage_journal_ocr(
    session: Session,
    *,
    user_id: str,
    attachment: str,
    caption: str,
    surface: str,
    conversation_id: str,
    message_id: str,
    author_user_id: str,
) -> StagedOcr:
    """Commit the OCR job for a journal upload; the worker saves the entry."""
    lock_active_user_for_write(session, user_id)
    job = _stage_job(
        session,
        user_id=user_id,
        metadata={
            "destination": "journal",
            "attachment": attachment,
            "caption": caption,
            "surface": surface,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "author_user_id": author_user_id,
        },
    )
    lock_active_user_for_write(session, user_id)
    session.commit()
    _dispatch(session, job)
    return StagedOcr(job_id=job.id)


def run_pdf_ocr(session: Session, *, job: IngestionJob, attempts: int) -> dict[str, Any]:
    """Read a staged PDF and finish its upload. Runs inside the ingestion job runner."""
    from thoughtpins.media.attachments import load_media_attachment

    user_id = job.user_id
    metadata = dict(job.metadata_json or {})
    library = metadata.get("destination") != "journal"
    document_id = str(metadata.get("document_id") or "")
    if library and _pending_document(session, user_id, document_id) is None:
        # Deleted meanwhile, or finished by an earlier delivery of this job.
        return {"type": "skipped", "entry_id": job.entry_id}
    content = load_media_attachment(session, user_id=user_id, reference=str(metadata.get("attachment") or ""))
    # Nothing is held while OCR runs: not a connection, and not the account row
    # that deletion waits on.
    session.commit()
    if content is None:
        extraction = MediaExtraction(kind="document", error="original_missing")
        message = "The original file is no longer available. Upload it again, or paste the text."
    elif attempts > MAX_ATTEMPTS:
        extraction = MediaExtraction(kind="document", error="pdf_ocr_timed_out")
        message = _TOO_LONG
    else:
        extraction = _read_pdf(content)
        message = unreadable_pdf_message(extraction.metadata)
    text = _combine(str(metadata.get("caption") or ""), extraction.text)
    if library:
        return _finish_library(session, user_id, document_id, text, extraction, message)
    return _finish_journal(session, user_id, metadata, text, message)


def _read_pdf(content: bytes) -> MediaExtraction:
    from thoughtpins.media.extraction import _get_ocr_reader
    from thoughtpins.media.pdf import extract_pdf_text, worker_limits

    extraction = extract_pdf_text(
        content, ".pdf", ocr_reader=lambda: _get_ocr_reader(require_timeout=True), limits=worker_limits()
    )
    logger.info("Worker PDF OCR read {} pages", len(extraction.metadata.get("ocr_pages") or []))
    return extraction


def _finish_library(
    session: Session,
    user_id: str,
    document_id: str,
    text: str,
    extraction: MediaExtraction,
    message: str,
) -> dict[str, Any]:
    from thoughtpins import library as library_module
    from thoughtpins.library_enrichment import dispatch_document_enrichment, prepare_document_enrichment

    try:
        lock_active_user_for_write(session, user_id)
    except ValueError:
        return {"type": "skipped", "entry_id": None}
    document = _pending_document(session, user_id, document_id)
    if document is None:
        return {"type": "skipped", "entry_id": None}
    raw = session.query(RawEntry).filter(RawEntry.user_id == user_id, RawEntry.id == document.raw_entry_id).one()
    metadata = dict(document.metadata_json or {})
    metadata["upload"] = dict(metadata.get("upload") or {}) | {"extraction": extraction.metadata}
    clean = clean_text(text)
    if len(clean) < 3:
        document.status = document.fetch_status = raw.processed_status = UNREADABLE_STATUS
        document.processing_error = raw.processing_error = message
        document.summary = message
        document.metadata_json = metadata
        raw.raw_text = raw_entry_text(document.title, message, None, UNREADABLE_STATUS, message)
        lock_active_user_for_write(session, user_id)
        session.commit()
        return {"type": "error", "entry_id": raw.id, "error": message}

    document.raw_text = clean
    document.summary = summarize_text(clean)
    document.status = document.fetch_status = raw.processed_status = "processed"
    document.metadata_json = metadata | {
        "reading_analysis": reading_analysis_metadata(
            title=document.title,
            text=clean,
            source_domain=None,
            source_url=None,
            author=None,
            published_at=None,
            publisher_hint=None,
        )
    }
    raw.raw_text = raw_entry_text(document.title, clean, None, "processed", None)
    chunks = chunk_text(clean)
    for index, (chunk, start, end) in enumerate(chunks):
        session.add(
            DocumentChunk(
                user_id=user_id,
                document_id=document.id,
                chunk_index=index,
                text=chunk,
                char_start=start,
                char_end=end,
                token_count=rough_token_count(chunk),
                created_at_utc=_utcnow(),
            )
        )
    memories = library_module._create_document_memories(session, document, raw, chunks, status="processed")
    enrichment = prepare_document_enrichment(session, document, raw, clean, status="processed", defer_vector_index=True)
    lock_active_user_for_write(session, user_id)
    session.commit()
    if enrichment is not None:
        dispatch_document_enrichment(session, enrichment)
    else:
        library_module.schedule_document_memory_indexing(memories)
    return {"type": "library_upload", "entry_id": raw.id}


def _finish_journal(
    session: Session, user_id: str, metadata: dict[str, Any], text: str, message: str
) -> dict[str, Any]:
    from thoughtpins.chat.engine import execute_chat_message

    if len(clean_text(text)) < 3:
        return {"type": "error", "entry_id": None, "error": message}
    result = execute_chat_message(
        session,
        "journal: " + text,
        user_id=user_id,
        surface=str(metadata.get("surface") or "upload"),
        conversation_id=str(metadata.get("conversation_id") or "uploads"),
        message_id=str(metadata.get("message_id") or ""),
        author_user_id=str(metadata.get("author_user_id") or ""),
    )
    error = result.metadata.get("error") if isinstance(result.metadata, dict) else None
    return {"type": "error" if error else "journal_upload", "entry_id": result.entry_id, "error": error}


def _pending_document(session: Session, user_id: str, document_id: str) -> DocumentSource | None:
    return (
        session.query(DocumentSource)
        .filter(
            DocumentSource.user_id == user_id,
            DocumentSource.id == document_id,
            DocumentSource.status == PENDING_STATUS,
        )
        .first()
    )


def _stage_job(session: Session, *, user_id: str, metadata: dict[str, Any]) -> IngestionJob:
    job = IngestionJob(
        user_id=user_id,
        source=OPERATION,
        raw_text="",
        status="pending",
        metadata_json={"operation": OPERATION, **metadata},
    )
    session.add(job)
    session.flush()
    return job


def _dispatch(session: Session, job: IngestionJob) -> None:
    from thoughtpins.jobs import IngestionDispatchUnavailable, dispatch_ingestion_job

    try:
        dispatch_ingestion_job(session, job, user_id=job.user_id)
    except IngestionDispatchUnavailable:
        # The upload and its job committed together; the worker relay retries
        # the handoff, so the upload must not look lost.
        pass


def _combine(caption: str, text: str) -> str:
    caption, text = (caption or "").strip(), (text or "").strip()
    return f"{caption}\n\n{text}" if caption and text else caption or text


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
