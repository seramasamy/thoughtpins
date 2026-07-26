"""Celery worker entry point for asynchronous ingestion."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from thoughtpins.config import config
from thoughtpins.jobs import recover_pending_jobs, run_ingestion_job
from thoughtpins.vault.transfers import recover_vault_import_sessions, run_vault_import_session

_recovery_lock = threading.Lock()
_last_recovery_monotonic = 0.0


def _utc_timestamp() -> str:
    return str(datetime.now(timezone.utc).timestamp())


def _redis_client():
    if not config.REDIS_URL:
        return None
    from redis import Redis

    return Redis.from_url(config.REDIS_URL, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)


def record_worker_heartbeat() -> None:
    client = _redis_client()
    if not client:
        return
    client.setex("thoughtpins:worker:heartbeat", config.WORKER_HEARTBEAT_TTL_SECONDS, _utc_timestamp())


def _recover_queue(label: str, recover: Callable[[], int]) -> int:
    try:
        return recover()
    except Exception:
        logger.exception("Worker {} recovery failed", label)
        return 0


def recover_jobs_if_due(*, force: bool = False) -> int:
    """Run the durable-job relay without blocking overlapping heartbeats."""
    global _last_recovery_monotonic

    now = time.monotonic()
    interval = max(10, config.WORKER_RECOVERY_INTERVAL_SECONDS)
    if not force and now - _last_recovery_monotonic < interval:
        return 0
    if not _recovery_lock.acquire(blocking=False):
        return 0
    try:
        now = time.monotonic()
        if not force and now - _last_recovery_monotonic < interval:
            return 0
        _last_recovery_monotonic = now
        recovered = _recover_queue("ingestion-job", recover_pending_jobs)
        vault_recovered = _recover_queue("vault-import", recover_vault_import_sessions)
        if recovered or vault_recovered:
            logger.info(
                "Worker relay dispatched {} ingestion job(s) and {} vault import(s)",
                recovered,
                vault_recovered,
            )
        return recovered + vault_recovered
    except Exception:
        logger.exception("Worker durable-job recovery failed")
        return 0
    finally:
        _recovery_lock.release()


def _build_celery_app():
    try:
        from celery import Celery
    except ImportError as exc:
        raise RuntimeError("Celery is not installed. Install thoughtpins[workers].") from exc

    broker = config.CELERY_BROKER_URL or config.REDIS_URL
    backend = config.CELERY_RESULT_BACKEND or config.REDIS_URL
    if not broker:
        raise RuntimeError("CELERY_BROKER_URL or REDIS_URL must be set for Celery workers.")

    app = Celery("thoughtpins", broker=broker, backend=backend)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_default_queue=config.CELERY_QUEUE_NAME,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        task_time_limit=900,
        task_soft_time_limit=840,
    )
    return app


celery_app = _build_celery_app()


def _on_worker_ready(sender=None, **kwargs) -> None:
    del sender, kwargs
    record_worker_heartbeat()
    recover_jobs_if_due(force=True)
    logger.info("Celery worker ready on queue {}", config.CELERY_QUEUE_NAME)


def _on_worker_heartbeat(sender=None, **kwargs) -> None:
    del sender, kwargs
    record_worker_heartbeat()
    recover_jobs_if_due()


def _on_worker_shutdown(sender=None, **kwargs) -> None:
    del sender, kwargs
    logger.info("Celery worker shutting down")


def _register_worker_signals() -> None:
    try:
        from celery.signals import heartbeat_sent, worker_ready, worker_shutdown
    except Exception as e:
        logger.warning("Celery signal registration skipped: {}", e)
        return

    worker_ready.connect(_on_worker_ready, weak=False)
    heartbeat_sent.connect(_on_worker_heartbeat, weak=False)
    worker_shutdown.connect(_on_worker_shutdown, weak=False)


_register_worker_signals()


@celery_app.task(name="thoughtpins.ingest_job", bind=True, max_retries=0)
def ingest_job_task(self, job_id: str, user_id: str | None = None) -> dict[str, Any]:
    record_worker_heartbeat()
    logger.info("Celery ingestion job started: {}", job_id)
    run_ingestion_job(job_id, tenant_user_id=user_id)
    record_worker_heartbeat()
    return {"job_id": job_id, "status": "submitted"}


def enqueue_celery_job(job_id: str, user_id: str | None = None) -> None:
    celery_app.send_task("thoughtpins.ingest_job", args=[job_id, user_id], queue=config.CELERY_QUEUE_NAME)


@celery_app.task(
    name="thoughtpins.vault_import",
    bind=True,
    max_retries=0,
    soft_time_limit=3_500,
    time_limit=3_600,
)
def vault_import_task(self, transfer_id: str, user_id: str | None = None) -> dict[str, Any]:
    del self
    record_worker_heartbeat()
    logger.info("Celery vault import started: {}", transfer_id)
    run_vault_import_session(transfer_id, tenant_user_id=user_id)
    record_worker_heartbeat()
    return {"transfer_id": transfer_id, "status": "submitted"}


def enqueue_celery_vault_import(transfer_id: str, user_id: str | None = None) -> None:
    celery_app.send_task("thoughtpins.vault_import", args=[transfer_id, user_id], queue=config.CELERY_QUEUE_NAME)


def main(argv: list[str] | None = None) -> None:
    """Run a production Celery worker with the repository's configured queue."""
    record_worker_heartbeat()
    worker_args = argv or [
        "worker",
        "--loglevel",
        config.LOG_LEVEL.upper(),
        "--concurrency",
        str(max(1, config.CELERY_WORKER_CONCURRENCY)),
        "--queues",
        config.CELERY_QUEUE_NAME,
    ]
    logger.info("Starting Celery worker with args: {}", " ".join(worker_args))
    celery_app.worker_main(worker_args)


if __name__ == "__main__":
    main()
