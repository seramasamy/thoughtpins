"""API lifecycle and conservative admission to synchronous request workers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI
from loguru import logger
from starlette.concurrency import run_in_threadpool

from thoughtpins.config import config
from thoughtpins.jobs import recover_pending_jobs
from thoughtpins.library import flush_document_indexing
from thoughtpins.startup_recovery import recover_orphaned_entries
from thoughtpins.store import init_db


def request_worker_limit(*, pool_size: int, max_overflow: int, current_limit: float) -> float:
    """Leave half a finite pool for nested usage sessions and background work.

    A request can hold a connection while its provider adapter meters usage in
    a second transaction. One worker per connection can therefore deadlock.
    This is a conservative per-process starting point, not a capacity proof for
    independent background executors or multiple API/worker processes.
    SQLAlchemy defines size=0 or overflow=-1 as unbounded; retain the existing
    thread limit for those explicitly configured pools.
    """
    if pool_size < 0 or max_overflow < -1:
        raise ValueError("DB_POOL_SIZE must be nonnegative and DB_MAX_OVERFLOW must be at least -1")
    if pool_size == 0 or max_overflow == -1:
        return current_limit
    capacity = pool_size + max_overflow
    if capacity < 2:
        raise ValueError("The API needs at least two database connections for request and usage transactions")
    return min(current_limit, capacity // 2)


@contextmanager
def request_worker_budget() -> Iterator[None]:
    """Set the shared AnyIO budget for this lifespan; restore it on every exit."""
    limiter = current_default_thread_limiter()
    original = limiter.total_tokens
    # SQLite uses SQLAlchemy's local pool defaults rather than DB_POOL_*.
    # Production validation requires PostgreSQL; do not pretend these settings
    # describe SQLite's pool or its separate single-writer limit.
    if not config.database_url_sync().startswith("sqlite"):
        limiter.total_tokens = request_worker_limit(
            pool_size=config.DB_POOL_SIZE, max_overflow=config.DB_MAX_OVERFLOW, current_limit=original
        )
        logger.info("API synchronous worker limit={}", limiter.total_tokens)
    try:
        yield
    finally:
        limiter.total_tokens = original


def _startup() -> None:
    init_db()
    if config.RUN_STARTUP_RECOVERY:
        recover_orphaned_entries()
    if config.PROCESS_ENTRIES_ASYNC:
        recover_pending_jobs()


def _shutdown() -> None:
    if not flush_document_indexing(timeout_seconds=config.DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS):
        logger.warning("Document vector indexing queue did not drain before shutdown")
    try:
        from thoughtpins.memory.vector_store import close_vector_store

        close_vector_store()
    except Exception as exc:
        # Shutdown is best effort; provider exceptions can contain source text.
        logger.debug("Vector store close skipped during shutdown: {}", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with request_worker_budget():
        await run_in_threadpool(_startup)
        logger.info("Thought Pins API started")
        try:
            yield
        finally:
            await run_in_threadpool(_shutdown)
