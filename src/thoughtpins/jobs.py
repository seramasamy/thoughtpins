"""Durable ingestion job tracking with a local thread-pool runner."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import IngestionJob, User
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.store import get_session
from thoughtpins.tenancy import tenant_context

_executor = ThreadPoolExecutor(max_workers=max(1, config.INGESTION_WORKER_THREADS))
_DISPATCHABLE_STATUSES = ("pending", "retry")
_CLAIMABLE_STATUSES = (*_DISPATCHABLE_STATUSES, "queued")
_QUEUE_DISPATCH_ERROR = "The processing queue is temporarily unavailable."


class IngestionDispatchUnavailable(RuntimeError):
    """Raised after a durable job is preserved for a later dispatch retry."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _job_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def create_ingestion_job(
    session: Session,
    *,
    user_id: str,
    text: str,
    source: str = "api",
    metadata: dict[str, Any] | None = None,
    dedup_key: str | None = None,
) -> IngestionJob:
    job = IngestionJob(
        user_id=user_id,
        raw_text=text,
        source=source,
        dedup_key=(dedup_key or "").strip() or None,
        status="pending",
        metadata_json=metadata or {},
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_or_create_ingestion_job(
    session: Session,
    *,
    user_id: str,
    text: str,
    source: str = "api",
    metadata: dict[str, Any] | None = None,
    dedup_key: str | None = None,
) -> tuple[IngestionJob, bool]:
    """Create one job per tenant key, including under concurrent retries."""
    normalized = (dedup_key or "").strip() or None
    if normalized:
        existing = (
            session.query(IngestionJob)
            .filter(IngestionJob.user_id == user_id, IngestionJob.dedup_key == normalized)
            .first()
        )
        if existing:
            return existing, False
    job = IngestionJob(
        user_id=user_id,
        raw_text=text,
        source=source,
        dedup_key=normalized,
        status="pending",
        metadata_json=metadata or {},
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if not normalized:
            raise
        existing = (
            session.query(IngestionJob)
            .filter(IngestionJob.user_id == user_id, IngestionJob.dedup_key == normalized)
            .first()
        )
        if not existing:
            raise
        return existing, False
    session.refresh(job)
    return job, True


def get_job(session: Session, *, user_id: str, job_id: str) -> IngestionJob | None:
    return (
        session.query(IngestionJob)
        .filter(
            IngestionJob.id == job_id,
            IngestionJob.user_id == user_id,
        )
        .first()
    )


def enqueue_ingestion_job(job_id: str, user_id: str | None = None) -> None:
    if config.INGESTION_QUEUE_BACKEND == "celery":
        from thoughtpins.worker import enqueue_celery_job

        enqueue_celery_job(job_id, user_id=user_id)
        return
    _executor.submit(run_ingestion_job, job_id, user_id)


def dispatch_ingestion_job(
    session: Session,
    job: IngestionJob,
    *,
    user_id: str,
    enqueue_fn: Callable[..., Any] | None = None,
) -> bool:
    """Atomically publish a durable job once.

    The database transition happens before broker publication. If publication
    fails, the job returns to ``retry`` so the worker relay can recover it.
    Duplicate HTTP requests and duplicate broker deliveries are harmless: only
    one caller can transition a job into ``queued`` and only one worker can
    later claim it.
    """
    if job.user_id != user_id:
        raise ValueError("Ingestion job does not belong to the active user")

    queued_at = _utcnow()
    transitioned = (
        session.query(IngestionJob)
        .filter(
            IngestionJob.id == job.id,
            IngestionJob.user_id == user_id,
            IngestionJob.status.in_(_DISPATCHABLE_STATUSES),
        )
        .update(
            {
                IngestionJob.status: "queued",
                IngestionJob.queued_at_utc: queued_at,
                IngestionJob.error: None,
                IngestionJob.finished_at_utc: None,
            },
            synchronize_session=False,
        )
    )
    session.commit()
    session.expire_all()
    if transitioned != 1:
        return False

    publish = enqueue_fn or enqueue_ingestion_job
    try:
        publish(job.id, user_id=user_id)
    except Exception as exc:
        session.rollback()
        # A broker may accept a task and still drop the connection before it
        # acknowledges the publish. Never move a job back once a worker has
        # claimed it; a later duplicate delivery will then be a no-op.
        (
            session.query(IngestionJob)
            .filter(
                IngestionJob.id == job.id,
                IngestionJob.user_id == user_id,
                IngestionJob.status == "queued",
            )
            .update(
                {
                    IngestionJob.status: "retry",
                    IngestionJob.error: _QUEUE_DISPATCH_ERROR,
                },
                synchronize_session=False,
            )
        )
        session.commit()
        session.expire_all()
        logger.warning("Ingestion job {} remains durable after queue dispatch failed", job.id)
        raise IngestionDispatchUnavailable(_QUEUE_DISPATCH_ERROR) from exc
    return True


def worker_health() -> dict[str, Any]:
    if config.INGESTION_QUEUE_BACKEND == "thread":
        return {
            "status": "ok",
            "backend": "thread",
            "max_workers": max(1, config.INGESTION_WORKER_THREADS),
        }

    if config.INGESTION_QUEUE_BACKEND != "celery":
        return {"status": "error", "backend": config.INGESTION_QUEUE_BACKEND, "detail": "Unknown backend"}

    if not config.REDIS_URL:
        return {"status": "error", "backend": "celery", "detail": "REDIS_URL required for heartbeat"}

    try:
        from redis import Redis

        client = Redis.from_url(config.REDIS_URL, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
        heartbeat = client.get("thoughtpins:worker:heartbeat")
        queue_depth: int | None = None
        try:
            queue_depth = int(client.llen(config.CELERY_QUEUE_NAME))
        except Exception:
            queue_depth = None
        if not heartbeat:
            return {
                "status": "error",
                "backend": "celery",
                "detail": "No worker heartbeat",
                "queue": config.CELERY_QUEUE_NAME,
                "queue_depth": queue_depth,
            }
        age = max(0, int(_utcnow().timestamp()) - int(float(heartbeat)))
        if age > config.WORKER_HEARTBEAT_TTL_SECONDS:
            return {
                "status": "error",
                "backend": "celery",
                "detail": f"Worker heartbeat stale ({age}s)",
                "queue": config.CELERY_QUEUE_NAME,
                "queue_depth": queue_depth,
            }
        return {
            "status": "ok",
            "backend": "celery",
            "heartbeat_age_seconds": age,
            "queue": config.CELERY_QUEUE_NAME,
            "queue_depth": queue_depth,
        }
    except Exception as e:
        return {"status": "error", "backend": "celery", "detail": str(e)[:200]}


def recover_pending_jobs() -> int:
    """Relay durable jobs and recover stale worker claims after restarts."""
    recovered = 0
    now = _utcnow()
    stale_before = now - timedelta(minutes=max(1, config.INGESTION_STALE_AFTER_MINUTES))

    users_session = get_session()
    try:
        user_ids = [
            row[0]
            for row in users_session.query(User.id)
            .filter(User.is_active == True)
            .order_by(User.created_at_utc.asc())
            .all()
        ]
    finally:
        users_session.close()

    for user_id in user_ids:
        session = get_session()
        try:
            with tenant_context(user_id):
                jobs = (
                    session.query(IngestionJob)
                    .filter(
                        IngestionJob.user_id == user_id,
                        IngestionJob.status.in_(["pending", "retry", "queued", "running"]),
                    )
                    .order_by(IngestionJob.created_at_utc.asc())
                    .limit(500)
                    .all()
                )
                jobs_to_dispatch: list[str] = []
                for job in jobs:
                    if job.status == "running" and job.started_at_utc and job.started_at_utc > stale_before:
                        continue
                    if job.status == "running":
                        job.status = "retry"
                        job.error = "Recovered stale running job after process restart."
                        metadata = dict(job.metadata_json or {})
                        metadata["last_recovery_reason"] = "stale_worker_claim"
                        metadata["last_recovered_at_utc"] = now.isoformat()
                        job.metadata_json = metadata
                    elif job.status == "queued" and job.queued_at_utc and job.queued_at_utc > stale_before:
                        continue
                    elif job.status == "queued":
                        job.status = "retry"
                        job.error = "Recovered a stale queue handoff after process restart."
                        metadata = dict(job.metadata_json or {})
                        metadata["last_recovery_reason"] = "stale_queue_handoff"
                        metadata["last_recovered_at_utc"] = now.isoformat()
                        job.metadata_json = metadata
                    jobs_to_dispatch.append(job.id)
                session.commit()

                for job_id in jobs_to_dispatch:
                    job = get_job(session, user_id=user_id, job_id=job_id)
                    if not job:
                        continue
                    try:
                        if dispatch_ingestion_job(session, job, user_id=user_id):
                            recovered += 1
                    except IngestionDispatchUnavailable:
                        # The retry state is durable. A later relay cycle will
                        # attempt the handoff again after the broker recovers.
                        continue
        finally:
            session.close()

    if recovered:
        logger.info("Dispatched {} recovered ingestion job(s)", recovered)
    return recovered


def run_ingestion_job(job_id: str, tenant_user_id: str | None = None) -> None:
    if config.is_production() and not tenant_user_id:
        raise RuntimeError("A tenant identity is required to process ingestion jobs")

    session = get_session()
    try:
        with tenant_context(tenant_user_id):
            claim = session.query(IngestionJob).filter(
                IngestionJob.id == job_id,
                IngestionJob.status.in_(_CLAIMABLE_STATUSES),
            )
            if tenant_user_id:
                claim = claim.filter(IngestionJob.user_id == tenant_user_id)
            claimed = claim.update(
                {
                    IngestionJob.status: "running",
                    IngestionJob.started_at_utc: _utcnow(),
                    IngestionJob.finished_at_utc: None,
                    IngestionJob.error: None,
                },
                synchronize_session=False,
            )
            session.commit()
            if claimed != 1:
                return

            job_query = session.query(IngestionJob).filter(IngestionJob.id == job_id)
            if tenant_user_id:
                job_query = job_query.filter(IngestionJob.user_id == tenant_user_id)
            job = job_query.one()

            metadata = dict(job.metadata_json or {})
            attempts = int(metadata.get("attempts", 0)) + 1
            metadata["attempts"] = attempts
            job.metadata_json = metadata
            session.commit()

            result = process_message(
                session,
                job.raw_text,
                user_id=job.user_id,
                source=job.source,
                author_user_id=job.user_id,
                occurred_at_utc=_job_datetime(metadata.get("occurred_at_utc")),
                force_journal=metadata.get("force_journal") is True,
                dedup_key=str(metadata.get("dedup_key") or ""),
                user_importance=metadata.get("user_importance"),
            )
            job.entry_id = result.get("entry_id") or None
            job.status = "completed" if result.get("type") != "error" else "failed"
            job.error = result.get("error")
            job.finished_at_utc = _utcnow()
            session.commit()
    except Exception as e:
        logger.exception("Ingestion job {} failed", job_id)
        session.rollback()
        with tenant_context(tenant_user_id):
            failed_job_query = session.query(IngestionJob).filter(IngestionJob.id == job_id)
            if tenant_user_id:
                failed_job_query = failed_job_query.filter(IngestionJob.user_id == tenant_user_id)
            job = failed_job_query.first()
        if job:
            metadata = dict(job.metadata_json or {})
            attempts = int(metadata.get("attempts", 0))
            metadata["last_error"] = str(e)[:1000]
            if attempts < config.INGESTION_MAX_RETRIES:
                job.status = "retry"
                job.error = str(e)[:1000]
                job.metadata_json = metadata
                job.finished_at_utc = _utcnow()
                session.commit()
                try:
                    dispatch_ingestion_job(session, job, user_id=job.user_id)
                except IngestionDispatchUnavailable:
                    logger.warning("Ingestion job {} will be relayed after the queue recovers", job.id)
                return

            metadata["dead_letter_at_utc"] = _utcnow().isoformat()
            metadata["dead_letter_reason"] = str(e)[:1000]
            job.status = "dead_letter"
            job.error = str(e)[:1000]
            job.metadata_json = metadata
            job.finished_at_utc = _utcnow()
            session.commit()
    finally:
        session.close()
