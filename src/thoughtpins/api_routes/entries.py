"""Entry ingestion, journal listing, and ingestion job API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_

from thoughtpins.audit import record_audit_event
from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import IngestionJob, RawEntry
from thoughtpins.importance import set_entry_importance
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.jobs import (
    IngestionDispatchUnavailable,
    dispatch_ingestion_job,
    enqueue_ingestion_job,
    get_job,
    get_or_create_ingestion_job,
)
from thoughtpins.memory.salience_store import entity_ids_for_entry, refresh_entity_salience
from thoughtpins.pagination import decode_cursor, encode_cursor
from thoughtpins.store import get_session
from thoughtpins.voice_archive import delete_voice_assets_for_entry


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)
    message_id: str = Field(default="", max_length=128)
    user_importance: int | None = Field(default=None, ge=1, le=5)
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": "Had lunch with Maya and talked about the product launch."},
                {"text": "This was a major turning point for me.", "user_importance": 5},
            ]
        }
    }

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be empty")
        return value


class IngestResponse(BaseModel):
    status: str
    entry_id: str
    job_id: str | None = None
    entities: int = 0
    events: int = 0
    memories: int = 0
    relationships: int = 0
    user_importance: int | None = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"status": "queued", "entry_id": "", "job_id": "job_abc123"},
                {"status": "ok", "entry_id": "entry_abc123", "entities": 2, "events": 1, "memories": 4},
            ]
        }
    }


class JobResponse(BaseModel):
    id: str
    status: str
    entry_id: str | None = None
    error: str | None = None
    created_at_utc: str | None = None
    queued_at_utc: str | None = None
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "job_abc123",
                    "status": "completed",
                    "entry_id": "entry_abc123",
                    "error": None,
                    "created_at_utc": "2026-05-22T06:00:00",
                    "queued_at_utc": "2026-05-22T06:00:00",
                    "started_at_utc": "2026-05-22T06:00:01",
                    "finished_at_utc": "2026-05-22T06:00:04",
                }
            ]
        }
    }


class JobsPageResponse(BaseModel):
    items: list[JobResponse]
    page: int
    limit: int
    total: int
    has_next: bool
    next_cursor: str | None = None


class EntryResponse(BaseModel):
    id: str
    created_at_utc: str
    local_date: str | None = None
    local_time: str | None = None
    source: str
    raw_text: str
    sensitivity: str
    processed_status: str
    processing_error: str | None = None
    user_importance: int | None = Field(default=None, ge=1, le=5)
    importance_source: str | None = None
    importance_updated_at: str | None = None
    contextual_salience: float | None = None
    salience_uncertainty: float | None = None
    salience_tier: str | None = None
    salience_model_version: str | None = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "entry_abc123",
                    "created_at_utc": "2026-05-22T06:00:00",
                    "local_date": "2026-05-22",
                    "local_time": "09:00",
                    "source": "api",
                    "raw_text": "Had lunch with Maya and discussed launch risk.",
                    "sensitivity": "personal",
                    "processed_status": "completed",
                    "processing_error": None,
                    "user_importance": 4,
                    "importance_source": "user",
                    "importance_updated_at": "2026-05-22T06:05:00",
                }
            ]
        }
    }


class EntriesPageResponse(BaseModel):
    items: list[EntryResponse]
    page: int
    limit: int
    total: int
    has_next: bool
    next_cursor: str | None = None
    model_config = {
        "json_schema_extra": {"examples": [{"items": [], "page": 1, "limit": 50, "total": 0, "has_next": False}]}
    }


class EntryStatusResponse(BaseModel):
    entry_id: str | None = None
    job_id: str | None = None
    status: str
    error: str | None = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"entry_id": "entry_abc123", "job_id": None, "status": "completed", "error": None},
                {"entry_id": None, "job_id": "job_abc123", "status": "pending", "error": None},
            ]
        }
    }


class EntryImportanceRequest(BaseModel):
    user_importance: int | None = Field(
        ...,
        ge=1,
        le=5,
        description="Explicit user importance from 1 to 5, or null to clear it.",
    )
    model_config = {"json_schema_extra": {"examples": [{"user_importance": 5}, {"user_importance": None}]}}


def create_entries_router(
    *,
    current_user_dependency: Callable,
    process_message_fn: Callable[..., dict[str, Any]] | None = None,
    enqueue_job_fn: Callable[..., Any] | None = None,
) -> APIRouter:
    router = APIRouter()
    process_fn = process_message_fn or process_message
    enqueue_fn = enqueue_job_fn or enqueue_ingestion_job

    @router.post("/ingest", response_model=IngestResponse, include_in_schema=False)
    @router.post(
        "/v1/entries",
        response_model=IngestResponse,
        responses={
            202: {
                "description": "Entry accepted for asynchronous processing.",
                "content": {
                    "application/json": {"example": {"status": "queued", "entry_id": "", "job_id": "job_abc123"}}
                },
            }
        },
    )
    async def ingest(
        req: IngestRequest,
        response: Response,
        user_id: str = Depends(current_user_dependency),
    ) -> IngestResponse:
        session = get_session()
        try:
            if config.PROCESS_ENTRIES_ASYNC:
                dedup_key = f"api:{req.message_id}" if req.message_id else None
                metadata: dict[str, object] = (
                    {"user_importance": req.user_importance} if req.user_importance is not None else {}
                )
                if dedup_key:
                    metadata["dedup_key"] = dedup_key
                job, created = get_or_create_ingestion_job(
                    session,
                    user_id=user_id,
                    text=req.text,
                    source="api",
                    metadata=metadata,
                    dedup_key=dedup_key,
                )
                if created:
                    record_audit_event(session, user_id=user_id, action="entry.queued", metadata={"job_id": job.id})
                dispatch_ingestion_job(session, job, user_id=user_id, enqueue_fn=enqueue_fn)
                session.refresh(job)
                response.status_code = 202 if job.status in {"pending", "retry", "queued", "running"} else 200
                return IngestResponse(
                    status="queued" if created else ("duplicate" if job.entry_id else job.status),
                    entry_id=job.entry_id or "",
                    job_id=job.id,
                    user_importance=req.user_importance,
                )

            result = process_fn(
                session,
                req.text,
                user_id=user_id,
                source="api",
                telegram_message_id=req.message_id,
                telegram_chat_id="",
                author_user_id=user_id,
                user_importance=req.user_importance,
            )
            if result["type"] == "duplicate":
                record_audit_event(
                    session,
                    user_id=user_id,
                    action="entry.duplicate",
                    metadata={"entry_id": result.get("entry_id", "")},
                )
                return IngestResponse(
                    status="duplicate",
                    entry_id=result.get("entry_id", ""),
                    user_importance=result.get("user_importance"),
                )

            stats = result.get("stats", {})
            record_audit_event(
                session,
                user_id=user_id,
                action="entry.created",
                metadata={"entry_id": result.get("entry_id", ""), "result_type": result["type"]},
            )
            return IngestResponse(
                status="ok" if result["type"] == "journal_stored" else result["type"],
                entry_id=result.get("entry_id", ""),
                entities=stats.get("entities", 0),
                events=stats.get("events", 0),
                memories=stats.get("memories", 0),
                relationships=stats.get("relationships", 0),
                user_importance=result.get("user_importance"),
            )
        except IngestionDispatchUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Entry processing is temporarily unavailable. Retry the same request.",
            ) from exc
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Ingest failed")
            raise HTTPException(status_code=500, detail="Entry processing failed") from e
        finally:
            session.close()

    @router.post(
        "/v1/entries/async",
        response_model=JobResponse,
        status_code=202,
        responses={
            202: {
                "description": "Entry accepted for asynchronous processing.",
                "content": {
                    "application/json": {
                        "example": {"id": "job_abc123", "status": "pending", "entry_id": None, "error": None}
                    }
                },
            }
        },
    )
    async def ingest_async(req: IngestRequest, user_id: str = Depends(current_user_dependency)) -> JobResponse:
        session = get_session()
        try:
            dedup_key = f"api:{req.message_id}" if req.message_id else None
            metadata: dict[str, object] = (
                {"user_importance": req.user_importance} if req.user_importance is not None else {}
            )
            if dedup_key:
                metadata["dedup_key"] = dedup_key
            job, created = get_or_create_ingestion_job(
                session,
                user_id=user_id,
                text=req.text,
                source="api",
                metadata=metadata,
                dedup_key=dedup_key,
            )
            if created:
                record_audit_event(session, user_id=user_id, action="entry.queued", metadata={"job_id": job.id})
            dispatch_ingestion_job(session, job, user_id=user_id, enqueue_fn=enqueue_fn)
            session.refresh(job)
            return _job_response(job)
        except IngestionDispatchUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Entry processing is temporarily unavailable. Retry the same request.",
            ) from exc
        finally:
            session.close()

    @router.get("/v1/jobs/{job_id}", response_model=JobResponse)
    async def job_status(job_id: str, user_id: str = Depends(current_user_dependency)) -> JobResponse:
        session = get_session()
        try:
            job = get_job(session, user_id=user_id, job_id=job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return _job_response(job)
        finally:
            session.close()

    @router.get("/v1/jobs", response_model=JobsPageResponse)
    async def list_jobs(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
        status: str | None = Query(
            None,
            max_length=32,
            pattern="^(pending|retry|queued|running|completed|failed|dead_letter|canceled)$",
        ),
        cursor: str | None = Query(None, max_length=1024),
        user_id: str = Depends(current_user_dependency),
    ) -> JobsPageResponse:
        session = get_session()
        try:
            query = session.query(IngestionJob).filter(IngestionJob.user_id == user_id)
            if status:
                query = query.filter(IngestionJob.status == status)
            total = query.count()
            if cursor:
                position = _decode_cursor(cursor, sort="jobs.created", direction="desc")
                query = query.filter(
                    or_(
                        IngestionJob.created_at_utc < position.occurred_at,
                        and_(
                            IngestionJob.created_at_utc == position.occurred_at,
                            IngestionJob.id < position.row_id,
                        ),
                    )
                )
            query = query.order_by(IngestionJob.created_at_utc.desc(), IngestionJob.id.desc())
            if not cursor:
                query = query.offset((page - 1) * limit)
            rows = query.limit(limit + 1).all()
            has_next = len(rows) > limit
            jobs = rows[:limit]
            return JobsPageResponse(
                items=[_job_response(job) for job in jobs],
                page=page,
                limit=limit,
                total=total,
                has_next=has_next,
                next_cursor=_next_cursor(
                    jobs,
                    has_next=has_next,
                    sort="jobs.created",
                    direction="desc",
                    timestamp_attr="created_at_utc",
                ),
            )
        finally:
            session.close()

    @router.post("/v1/jobs/{job_id}/retry", response_model=JobResponse, status_code=202)
    async def retry_job(job_id: str, user_id: str = Depends(current_user_dependency)) -> JobResponse:
        session = get_session()
        try:
            job = get_job(session, user_id=user_id, job_id=job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            if job.status not in {"failed", "dead_letter", "retry"}:
                raise HTTPException(status_code=409, detail=f"Job is not retryable from status {job.status}")
            metadata = dict(job.metadata_json or {})
            metadata["manual_retry_at_utc"] = _utcnow().isoformat()
            job.metadata_json = metadata
            job.status = "retry"
            job.error = None
            job.finished_at_utc = None
            session.commit()
            record_audit_event(session, user_id=user_id, action="job.retry", metadata={"job_id": job.id})
            try:
                dispatch_ingestion_job(session, job, user_id=user_id, enqueue_fn=enqueue_fn)
            except IngestionDispatchUnavailable as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Entry processing is temporarily unavailable. Retry this job.",
                ) from exc
            session.refresh(job)
            return _job_response(job)
        finally:
            session.close()

    @router.post("/v1/jobs/{job_id}/cancel", response_model=JobResponse)
    async def cancel_job(job_id: str, user_id: str = Depends(current_user_dependency)) -> JobResponse:
        session = get_session()
        try:
            job = get_job(session, user_id=user_id, job_id=job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            if job.status not in {"pending", "retry", "queued"}:
                raise HTTPException(status_code=409, detail=f"Job cannot be canceled from status {job.status}")
            job.status = "canceled"
            job.finished_at_utc = _utcnow()
            session.commit()
            record_audit_event(session, user_id=user_id, action="job.cancel", metadata={"job_id": job.id})
            return _job_response(job)
        finally:
            session.close()

    @router.get("/v1/entries", response_model=EntriesPageResponse)
    async def list_entries(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=200),
        include_private: bool = Query(False),
        cursor: str | None = Query(None, max_length=1024),
        user_id: str = Depends(current_user_dependency),
    ) -> EntriesPageResponse:
        session = get_session()
        try:
            query = session.query(RawEntry).filter(RawEntry.user_id == user_id)
            if not include_private:
                query = query.filter(RawEntry.is_private == False)
            total = query.count()
            if cursor:
                position = _decode_cursor(cursor, sort="entries.created", direction="desc")
                query = query.filter(
                    or_(
                        RawEntry.created_at_utc < position.occurred_at,
                        and_(RawEntry.created_at_utc == position.occurred_at, RawEntry.id < position.row_id),
                    )
                )
            query = query.order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
            if not cursor:
                query = query.offset((page - 1) * limit)
            rows = query.limit(limit + 1).all()
            has_next = len(rows) > limit
            entries = rows[:limit]
            return EntriesPageResponse(
                items=[_entry_response(entry) for entry in entries],
                page=page,
                limit=limit,
                total=total,
                has_next=has_next,
                next_cursor=_next_cursor(
                    entries,
                    has_next=has_next,
                    sort="entries.created",
                    direction="desc",
                    timestamp_attr="created_at_utc",
                ),
            )
        finally:
            session.close()

    @router.get("/v1/entries/{entry_id}/status", response_model=EntryStatusResponse)
    async def entry_status(entry_id: str, user_id: str = Depends(current_user_dependency)) -> EntryStatusResponse:
        session = get_session()
        try:
            entry = (
                session.query(RawEntry)
                .filter(
                    RawEntry.id == entry_id,
                    RawEntry.user_id == user_id,
                )
                .first()
            )
            if entry:
                return EntryStatusResponse(
                    entry_id=entry.id,
                    status=entry.processed_status,
                    error=entry.processing_error,
                )

            job = (
                session.query(IngestionJob)
                .filter(
                    IngestionJob.id == entry_id,
                    IngestionJob.user_id == user_id,
                )
                .first()
            )
            if job:
                return EntryStatusResponse(
                    job_id=job.id,
                    entry_id=job.entry_id,
                    status=job.status,
                    error=job.error,
                )
            raise HTTPException(status_code=404, detail="Entry or job not found")
        finally:
            session.close()

    @router.get("/v1/entries/{entry_id}", response_model=EntryResponse)
    async def get_entry(entry_id: str, user_id: str = Depends(current_user_dependency)) -> EntryResponse:
        session = get_session()
        try:
            entry = (
                session.query(RawEntry)
                .filter(
                    RawEntry.id == entry_id,
                    RawEntry.user_id == user_id,
                )
                .first()
            )
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")
            return _entry_response(entry)
        finally:
            session.close()

    @router.patch("/v1/entries/{entry_id}/importance", response_model=EntryResponse)
    async def update_entry_importance(
        entry_id: str,
        req: EntryImportanceRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> EntryResponse:
        session = get_session()
        try:
            updated = set_entry_importance(
                session,
                user_id=user_id,
                entry_id=entry_id,
                value=req.user_importance,
                source="api",
            )
            if not updated:
                raise HTTPException(status_code=404, detail="Entry not found")
            session.commit()
            entry = (
                session.query(RawEntry)
                .filter(
                    RawEntry.id == entry_id,
                    RawEntry.user_id == user_id,
                )
                .one()
            )
            return _entry_response(entry)
        finally:
            session.close()

    @router.delete("/v1/entries/{entry_id}")
    async def delete_entry(entry_id: str, user_id: str = Depends(current_user_dependency)) -> dict[str, str]:
        session = get_session()
        try:
            entry = (
                session.query(RawEntry)
                .filter(
                    RawEntry.id == entry_id,
                    RawEntry.user_id == user_id,
                )
                .first()
            )
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")
            memory_ids = [memory.id for memory in entry.memories]
            affected_entity_ids = entity_ids_for_entry(session, entry.id)
            delete_voice_assets_for_entry(session, user_id=user_id, raw_entry_id=entry.id)
            session.delete(entry)
            session.flush()
            refresh_entity_salience(
                session,
                user_id=user_id,
                entity_ids=affected_entity_ids,
            )
            session.commit()
            if memory_ids:
                try:
                    from thoughtpins.memory.vector_store import get_vector_store

                    get_vector_store().delete(memory_ids)
                except Exception as e:
                    logger.warning("Vector cleanup failed for entry {}: {}", entry_id, e)
            record_audit_event(session, user_id=user_id, action="entry.deleted", metadata={"entry_id": entry_id})
            return {"status": "deleted", "entry_id": entry_id}
        finally:
            session.close()

    return router


def _entry_response(entry: RawEntry) -> EntryResponse:
    return EntryResponse(
        id=entry.id,
        created_at_utc=entry.created_at_utc.isoformat() if entry.created_at_utc else "",
        local_date=entry.local_date.isoformat() if entry.local_date else None,
        local_time=entry.local_time,
        source=entry.source,
        raw_text=maybe_decrypt_text(entry.raw_text),
        sensitivity=entry.sensitivity,
        processed_status=entry.processed_status,
        processing_error=entry.processing_error,
        user_importance=entry.user_importance,
        importance_source=entry.importance_source,
        importance_updated_at=(entry.importance_updated_at.isoformat() if entry.importance_updated_at else None),
        contextual_salience=entry.contextual_salience,
        salience_uncertainty=entry.salience_uncertainty,
        salience_tier=(str((entry.analysis_json or {}).get("salience", {}).get("tier") or "") or None),
        salience_model_version=entry.salience_model_version,
    )


def _job_response(job) -> JobResponse:
    return JobResponse(
        id=job.id,
        status=job.status,
        entry_id=job.entry_id,
        error=job.error,
        created_at_utc=job.created_at_utc.isoformat() if job.created_at_utc else None,
        queued_at_utc=job.queued_at_utc.isoformat() if job.queued_at_utc else None,
        started_at_utc=job.started_at_utc.isoformat() if job.started_at_utc else None,
        finished_at_utc=job.finished_at_utc.isoformat() if job.finished_at_utc else None,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _decode_cursor(value: str, *, sort: str, direction: str):
    try:
        return decode_cursor(value, sort=sort, direction=direction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _next_cursor(
    rows: list[Any],
    *,
    has_next: bool,
    sort: str,
    direction: str,
    timestamp_attr: str,
) -> str | None:
    if not has_next or not rows:
        return None
    last = rows[-1]
    occurred_at = getattr(last, timestamp_attr)
    if not isinstance(occurred_at, datetime):
        return None
    return encode_cursor(
        sort=sort,
        direction=direction,
        occurred_at=occurred_at,
        row_id=last.id,
    )
