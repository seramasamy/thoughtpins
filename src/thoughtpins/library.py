"""Article and document memory ingestion.

Journal entries describe the user's lived experience. Library sources describe
external content the user read or saved. Both become searchable memories, but
the source type and provenance stay explicit.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins import article_fetch as _article_fetch
from thoughtpins.article_fetch import FetchedSource
from thoughtpins.config import config
from thoughtpins.db import DocumentChunk, DocumentSource, Memory, RawEntry
from thoughtpins.importance import normalize_user_importance
from thoughtpins.ingestion.pipeline import _resolve_owner_user_id
from thoughtpins.library_text import (
    CHUNK_CHARS as _CHUNK_CHARS,
)
from thoughtpins.library_text import (
    CHUNK_OVERLAP as _CHUNK_OVERLAP,
)
from thoughtpins.library_text import (
    chunk_text as _chunk_text,
)
from thoughtpins.library_text import (
    clean_text as _clean_text,
)
from thoughtpins.library_text import (
    raw_entry_text as _raw_entry_text,
)
from thoughtpins.library_text import (
    rough_token_count as _rough_token_count,
)
from thoughtpins.library_text import (
    summarize_text as _summarize_text,
)
from thoughtpins.library_text import (
    title_from_text as _title_from_text,
)
from thoughtpins.reading_analysis import reading_analysis_metadata
from thoughtpins.utils import hash_text, local_today

DEFAULT_RIGHTS_BASIS = "user_provided"
CHUNK_CHARS = _CHUNK_CHARS
CHUNK_OVERLAP = _CHUNK_OVERLAP
IndexPayload = list[tuple[str, str, str]]


@dataclass(frozen=True)
class _IndexBatch:
    payload: IndexPayload
    indexer: Callable[[IndexPayload], None]


_INDEX_QUEUE: queue.Queue[_IndexBatch] = queue.Queue()
_INDEX_WORKER_LOCK = threading.Lock()
_INDEX_WORKER_READY = threading.Event()

_fetch_with_local_http = _article_fetch._fetch_with_local_http
_fetch_with_jina_reader = _article_fetch._fetch_with_jina_reader
_fetch_with_firecrawl = _article_fetch._fetch_with_firecrawl
_fetch_with_apify = _article_fetch._fetch_with_apify
_apify_actor_path = _article_fetch._apify_actor_path
_apify_input_payload = _article_fetch._apify_input_payload
_extract_apify_item = _article_fetch._extract_apify_item

# Kept as public aliases for transport adapters and third-party extensions.
article_fetch_health = _article_fetch.article_fetch_health
extract_urls = _article_fetch.extract_urls


def fetch_url_text(url: str) -> FetchedSource:
    """Compatibility wrapper around the modular URL fetcher."""
    _article_fetch._fetch_with_local_http = _fetch_with_local_http
    _article_fetch._fetch_with_jina_reader = _fetch_with_jina_reader
    _article_fetch._fetch_with_firecrawl = _fetch_with_firecrawl
    _article_fetch._fetch_with_apify = _fetch_with_apify
    return _article_fetch.fetch_url_text(url)


@dataclass
class LibraryIngestResult:
    document_id: str
    raw_entry_id: str
    title: str
    source_type: str
    status: str
    chunks: int
    memories: int
    source_url: str | None = None
    error: str | None = None
    duplicate: bool = False
    access_method: str | None = None
    rights_basis: str | None = None
    paywall_detected: bool = False
    user_importance: int | None = None


def ingest_url(
    session: Session,
    url: str,
    *,
    user_id: str | None = None,
    telegram_chat_id: str = "",
    note: str = "",
    defer_vector_index: bool = False,
    user_importance: int | None = None,
) -> LibraryIngestResult:
    fetched = fetch_url_text(url)
    cleaned_note = _clean_text(note)
    use_user_text = fetched.status != "processed" and len(cleaned_note) >= config.ARTICLE_MIN_TEXT_CHARS
    if use_user_text:
        text = cleaned_note
        status = "processed"
        processing_error = None
        access_method = "user_paste"
        rights_basis = "user_provided"
        metadata = fetched.metadata | {
            "user_note_promoted_to_text": True,
            "original_fetch_status": fetched.status,
            "original_fetch_error": fetched.error,
        }
    else:
        text = (
            cleaned_note or f"Saved link metadata for {fetched.url}"
            if fetched.rights_basis == "metadata_only"
            else fetched.text or cleaned_note or f"Saved link metadata for {fetched.url}"
        )
        status = fetched.status
        processing_error = fetched.error
        access_method = fetched.access_method
        rights_basis = fetched.rights_basis
        metadata = fetched.metadata | {"user_note": cleaned_note} if cleaned_note else fetched.metadata
    title = fetched.title or urlparse(url).netloc or "Saved link"
    return ingest_document_text(
        session,
        text,
        user_id=user_id,
        telegram_chat_id=telegram_chat_id,
        source_type="url",
        title=title,
        author=fetched.author,
        original_url=fetched.original_url,
        source_url=fetched.url,
        canonical_url=fetched.canonical_url or fetched.url,
        source_domain=fetched.source_domain,
        access_method=access_method,
        rights_basis=rights_basis,
        fetch_status=fetched.fetch_status,
        paywall_detected=fetched.paywall_detected,
        retrieval_quality_score=fetched.retrieval_quality_score,
        published_at=fetched.published_at,
        status=status,
        processing_error=processing_error,
        metadata_json=metadata,
        defer_vector_index=defer_vector_index,
        user_importance=user_importance,
    )


def ingest_document_text(
    session: Session,
    text: str,
    *,
    user_id: str | None = None,
    telegram_chat_id: str = "",
    source_type: str = "text",
    title: str = "",
    author: str | None = None,
    original_url: str | None = None,
    source_url: str | None = None,
    canonical_url: str | None = None,
    source_domain: str | None = None,
    access_method: str = "user_paste",
    rights_basis: str = DEFAULT_RIGHTS_BASIS,
    fetch_status: str | None = None,
    paywall_detected: bool = False,
    retrieval_quality_score: float | None = None,
    published_at: datetime | None = None,
    status: str = "processed",
    processing_error: str | None = None,
    metadata_json: dict | None = None,
    defer_vector_index: bool = False,
    user_importance: int | None = None,
) -> LibraryIngestResult:
    clean_text = _clean_text(text)
    if len(clean_text) < 3:
        raise ValueError("Document text is empty")

    owner_user_id = _resolve_owner_user_id(session, user_id=user_id, telegram_chat_id=telegram_chat_id)
    normalized_importance = normalize_user_importance(user_importance)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today = local_today()
    content_hash = hash_text(f"{source_url or ''}\n{clean_text}")

    existing = (
        session.query(DocumentSource)
        .filter(DocumentSource.user_id == owner_user_id, DocumentSource.content_hash == content_hash)
        .first()
    )
    if existing:
        if (
            normalized_importance is not None
            and existing.raw_entry
            and existing.raw_entry.user_importance != normalized_importance
        ):
            existing.raw_entry.user_importance = normalized_importance
            existing.raw_entry.importance_source = "ingest"
            existing.raw_entry.importance_updated_at = now_utc
            session.commit()
        return LibraryIngestResult(
            document_id=existing.id,
            raw_entry_id=existing.raw_entry_id,
            title=existing.title,
            source_type=existing.source_type,
            status=existing.status,
            chunks=len(existing.chunks),
            memories=session.query(Memory)
            .filter(
                Memory.user_id == owner_user_id,
                Memory.source_provenance == f"document:{existing.id}",
            )
            .count(),
            source_url=existing.source_url,
            error=existing.processing_error,
            duplicate=True,
            access_method=existing.access_method,
            rights_basis=existing.rights_basis,
            paywall_detected=bool(existing.paywall_detected),
            user_importance=existing.raw_entry.user_importance if existing.raw_entry else None,
        )

    safe_title = _title_from_text(clean_text, source_url=source_url, title=title)
    raw = RawEntry(
        user_id=owner_user_id,
        created_at_utc=now_utc,
        local_date=today,
        local_time=now_utc.strftime("%H:%M"),
        source="library_url" if source_type == "url" else "library_doc",
        telegram_chat_id=telegram_chat_id,
        raw_text=_raw_entry_text(safe_title, clean_text, source_url, status, processing_error),
        content_hash=content_hash,
        is_private=False,
        sensitivity="personal",
        processed_status=status,
        processing_error=processing_error,
        user_importance=normalized_importance,
        importance_source="ingest" if normalized_importance is not None else None,
        importance_updated_at=now_utc if normalized_importance is not None else None,
    )
    session.add(raw)
    session.flush()

    resolved_domain = source_domain or (urlparse(source_url).hostname if source_url else None)
    source_metadata = metadata_json or {}
    publisher_hint = str(source_metadata.get("publication") or source_metadata.get("site_name") or "").strip() or None
    reading_analysis = reading_analysis_metadata(
        title=safe_title,
        text=clean_text,
        source_domain=resolved_domain,
        source_url=source_url,
        author=author,
        published_at=published_at,
        publisher_hint=publisher_hint,
    )
    enriched_metadata = (metadata_json or {}) | {"reading_analysis": reading_analysis}

    document = DocumentSource(
        user_id=owner_user_id,
        raw_entry_id=raw.id,
        source_type=source_type,
        title=safe_title,
        author=author,
        original_url=original_url,
        source_url=source_url,
        canonical_url=canonical_url or source_url,
        source_domain=resolved_domain,
        access_method=access_method,
        rights_basis=rights_basis,
        fetch_status=fetch_status or status,
        paywall_detected=paywall_detected,
        retrieval_quality_score=retrieval_quality_score,
        published_at=published_at,
        content_hash=content_hash,
        raw_text=clean_text,
        summary=_summarize_text(clean_text),
        status=status,
        processing_error=processing_error,
        sensitivity="personal",
        created_at_utc=now_utc,
        local_date=today,
        metadata_json=enriched_metadata,
    )
    session.add(document)
    session.flush()

    chunks = _chunk_text(clean_text) if status == "processed" else []
    for index, (chunk, start, end) in enumerate(chunks):
        session.add(
            DocumentChunk(
                user_id=owner_user_id,
                document_id=document.id,
                chunk_index=index,
                text=chunk,
                char_start=start,
                char_end=end,
                token_count=_rough_token_count(chunk),
                created_at_utc=now_utc,
            )
        )

    memories = _create_document_memories(session, document, raw, chunks, status=status)
    graph_stats = _extract_document_graph(session, document, raw, clean_text, status=status)
    if graph_stats:
        document.metadata_json = (document.metadata_json or {}) | {"graph_extraction": graph_stats}
    _mirror_document_to_graph_backend(session, document, raw, clean_text, status=status)
    session.commit()
    if defer_vector_index:
        schedule_document_memory_indexing(memories)
    else:
        _index_document_memories(memories)

    return LibraryIngestResult(
        document_id=document.id,
        raw_entry_id=raw.id,
        title=document.title,
        source_type=document.source_type,
        status=document.status,
        chunks=len(chunks),
        memories=len(memories),
        source_url=document.source_url,
        error=document.processing_error,
        duplicate=False,
        access_method=document.access_method,
        rights_basis=document.rights_basis,
        paywall_detected=bool(document.paywall_detected),
        user_importance=raw.user_importance,
    )


def list_documents(session: Session, user_id: str, *, limit: int = 20) -> list[DocumentSource]:
    return (
        session.query(DocumentSource)
        .filter(DocumentSource.user_id == user_id)
        .order_by(DocumentSource.created_at_utc.desc())
        .limit(limit)
        .all()
    )


def find_document(session: Session, user_id: str, reference: str) -> DocumentSource | None:
    ref = (reference or "").strip()
    if not ref:
        return None
    exact = (
        session.query(DocumentSource)
        .filter(
            DocumentSource.user_id == user_id,
            DocumentSource.id == ref,
        )
        .first()
    )
    if exact:
        return exact
    if len(ref) >= 6:
        by_prefix = (
            session.query(DocumentSource)
            .filter(
                DocumentSource.user_id == user_id,
                DocumentSource.id.ilike(f"{ref}%"),
            )
            .first()
        )
        if by_prefix:
            return by_prefix
    return (
        session.query(DocumentSource)
        .filter(
            DocumentSource.user_id == user_id,
            DocumentSource.title.ilike(f"%{ref}%"),
        )
        .order_by(DocumentSource.created_at_utc.desc())
        .first()
    )


def _create_document_memories(
    session: Session,
    document: DocumentSource,
    raw: RawEntry,
    chunks: list[tuple[str, int, int]],
    *,
    status: str,
) -> list[Memory]:
    memories: list[Memory] = []
    summary_text = (
        f"Source saved: {document.title}. "
        f"Type: {document.source_type}. "
        f"Status: {status}. "
        f"Access: {document.access_method or 'unknown'}. "
        f"Rights basis: {document.rights_basis or 'unknown'}. "
        f"Summary: {document.summary or 'No summary available.'}"
    )
    if document.source_url:
        summary_text += f" URL: {document.source_url}"
    summary = Memory(
        user_id=document.user_id,
        raw_entry_id=raw.id,
        memory_type="source_summary",
        text=summary_text,
        structured_json={
            "source_kind": "document",
            "document_id": document.id,
            "title": document.title,
            "source_url": document.source_url,
            "status": status,
            "access_method": document.access_method,
            "rights_basis": document.rights_basis,
            "paywall_detected": bool(document.paywall_detected),
        },
        local_date=document.local_date,
        sensitivity=document.sensitivity,
        confidence="observed_by_user",
        source_provenance=f"document:{document.id}",
        created_at_utc=document.created_at_utc,
    )
    session.add(summary)
    memories.append(summary)

    reading_analysis = (document.metadata_json or {}).get("reading_analysis", {})
    if isinstance(reading_analysis, dict):
        publisher = str(reading_analysis.get("publisher") or document.source_domain or "Unknown source")
        topics = [str(item) for item in reading_analysis.get("topics", []) if str(item).strip()]
        concepts = [str(item) for item in reading_analysis.get("key_concepts", []) if str(item).strip()]
        profile_bits = [
            f"Reading profile: '{document.title}'",
            f"Source: {publisher}",
        ]
        if document.source_domain:
            profile_bits.append(f"Domain: {document.source_domain}")
        if document.author:
            profile_bits.append(f"Author: {document.author}")
        if topics:
            profile_bits.append("Topics: " + ", ".join(topics))
        if concepts:
            profile_bits.append("Key concepts: " + ", ".join(concepts[:12]))
        profile = Memory(
            user_id=document.user_id,
            raw_entry_id=raw.id,
            memory_type="source_characteristics",
            text=". ".join(profile_bits) + ".",
            structured_json={
                "source_kind": "document",
                "document_id": document.id,
                "title": document.title,
                "publisher": publisher,
                "source_domain": document.source_domain,
                "source_url": document.source_url,
                "topics": topics,
                "key_concepts": concepts,
                "word_count": reading_analysis.get("word_count"),
            },
            local_date=document.local_date,
            sensitivity=document.sensitivity,
            confidence="observed_by_user",
            source_provenance=f"document:{document.id}",
            created_at_utc=document.created_at_utc,
        )
        session.add(profile)
        memories.append(profile)

    if status != "processed":
        return memories

    for index, (chunk, start, end) in enumerate(chunks):
        memory = Memory(
            user_id=document.user_id,
            raw_entry_id=raw.id,
            memory_type="source_excerpt",
            text=f"From source '{document.title}' chunk {index + 1}: {chunk}",
            structured_json={
                "source_kind": "document",
                "document_id": document.id,
                "title": document.title,
                "source_url": document.source_url,
                "access_method": document.access_method,
                "rights_basis": document.rights_basis,
                "chunk_index": index,
                "char_start": start,
                "char_end": end,
                "evidence_text": chunk,
            },
            local_date=document.local_date,
            sensitivity=document.sensitivity,
            confidence="observed_by_user",
            source_provenance=f"document:{document.id}",
            created_at_utc=document.created_at_utc,
        )
        session.add(memory)
        memories.append(memory)
    session.flush()
    return memories


def _index_document_memories(memories: list[Memory]) -> None:
    _index_document_memory_payloads(
        [(memory.id, memory.text, memory.user_id) for memory in memories if memory.id and memory.text]
    )


def schedule_document_memory_indexing(memories: list[Memory]) -> None:
    payload = [(memory.id, memory.text, memory.user_id) for memory in memories if memory.id and memory.text]
    if not payload:
        return
    _ensure_index_worker()
    # Capture the dispatcher with the batch. A later runtime reconfiguration
    # cannot change work that has already been accepted by the queue.
    _INDEX_QUEUE.put(_IndexBatch(payload=payload, indexer=_index_document_memory_payloads))


def document_indexing_backlog() -> int:
    return int(getattr(_INDEX_QUEUE, "unfinished_tasks", _INDEX_QUEUE.qsize()))


def flush_document_indexing(timeout_seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    if document_indexing_backlog() == 0:
        return True
    while time.monotonic() < deadline:
        if document_indexing_backlog() == 0:
            return True
        time.sleep(0.05)
    return document_indexing_backlog() == 0


def _ensure_index_worker() -> None:
    if _INDEX_WORKER_READY.is_set():
        return
    with _INDEX_WORKER_LOCK:
        if _INDEX_WORKER_READY.is_set():
            return
        worker = threading.Thread(target=_index_worker_loop, name="thoughtpins-document-index", daemon=True)
        worker.start()
        _INDEX_WORKER_READY.set()


def _index_worker_loop() -> None:
    while True:
        batch = _INDEX_QUEUE.get()
        try:
            batch.indexer(batch.payload)
        finally:
            _INDEX_QUEUE.task_done()


def _index_document_memory_payloads(payload: IndexPayload) -> None:
    if not payload:
        return
    try:
        from thoughtpins.memory.vector_store import get_vector_store

        ids = [memory_id for memory_id, _, _ in payload]
        texts = [text for _, text, _ in payload]
        metadata = [{"user_id": user_id} for _, _, user_id in payload]
        get_vector_store().add(ids, texts, metadata)
    except Exception as exc:
        logger.warning("Document memory vector indexing failed: {}", exc)


def _extract_document_graph(
    session: Session,
    document: DocumentSource,
    raw: RawEntry,
    text: str,
    *,
    status: str,
) -> dict | None:
    """Optionally extract typed graph facts from document content.

    The SQL document rows remain the source of truth. Graph extraction is a
    derived enrichment and must never make URL ingestion fail.
    """
    if status != "processed" or not config.LIBRARY_EXTRACT_GRAPH:
        return None
    graph_text = _clean_text(text)[: config.LIBRARY_GRAPH_EXTRACT_MAX_CHARS]
    # ARTICLE_MIN_TEXT_CHARS guards web fetching, where a short result means a
    # paywall stub or a failed retrieval. It is the wrong bar for text the person
    # wrote themselves: most notes in a real Obsidian vault, and most pasted
    # snippets, are a couple of hundred characters, and gating on 500 left every
    # one of them out of the graph with no people, places, or topics extracted.
    if len(graph_text) < config.LIBRARY_GRAPH_MIN_TEXT_CHARS:
        return None
    try:
        from thoughtpins.ingestion.extraction import correct_entity_types, extract_from_entry
        from thoughtpins.ingestion.pipeline import (
            _auto_link_entities_to_memories,
            _normalize_sensitivity,
            _store_extraction,
        )

        local_datetime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        extraction_input = (
            f"External reading source: {document.title}\n"
            f"Source URL: {document.source_url or document.original_url or ''}\n\n"
            f"{graph_text}"
        )
        extraction = extract_from_entry(extraction_input, local_datetime)
        _normalize_sensitivity(extraction)
        extraction = correct_entity_types(extraction, extraction_input)
        stats = _store_extraction(
            session, raw, extraction, document.local_date or local_today(), raw_text=extraction_input
        )
        _auto_link_entities_to_memories(session, raw.id)
        raw.processed_status = "completed"
        return stats
    except Exception as exc:
        logger.warning("Document graph extraction skipped for {}: {}", document.id, str(exc)[:200])
        raw.processing_error = raw.processing_error or f"Document graph extraction skipped: {str(exc)[:200]}"
        return {"skipped": True, "error": str(exc)[:200]}


def _mirror_document_to_graph_backend(
    session: Session,
    document: DocumentSource,
    raw: RawEntry,
    text: str,
    *,
    status: str,
) -> None:
    if status != "processed":
        return
    try:
        from thoughtpins.memory.graph_backend import GraphEpisode, add_episode_to_graph_backend

        add_episode_to_graph_backend(
            session,
            GraphEpisode(
                user_id=document.user_id,
                episode_id=document.id,
                name=f"document_{document.id}",
                body=text[: config.LIBRARY_GRAPH_EXTRACT_MAX_CHARS],
                source="text",
                source_description=f"Thought Pins reading source: {document.source_type}",
                reference_time=document.created_at_utc,
                metadata={
                    "document_id": document.id,
                    "raw_entry_id": raw.id,
                    "title": document.title,
                    "source_url": document.source_url,
                    "rights_basis": document.rights_basis,
                },
            ),
        )
    except Exception as exc:
        logger.debug("Graph backend mirror skipped for document {}: {}", document.id, str(exc)[:160])
