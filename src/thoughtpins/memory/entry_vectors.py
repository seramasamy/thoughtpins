"""Write a saved entry's memories to the vector index once the save has committed.

Every web, iOS and Android save used to stop at PostgreSQL (TD-008), so the
vector channel only held what a manual reindex had put there. The index is
derived state and a save must never depend on it: indexing runs after the
commit, off the request (its own worker task in production), and an embedding
failure leaves the entry saved and its memories unindexed. The repair sweep
finds live memories with no vector and indexes them. The worker runs it over
every memory at start-up and over recent ones on an interval, which makes it
both the retry for failed indexing and the backfill for older entries.

A vector's payload holds its memory's text, so deletion must win every race:

- Account deletion takes the user row FOR UPDATE and deletes vectors before it
  commits. The upsert here holds that row FOR SHARE, so either the deletion
  waits and then removes what was written, or the upsert finds the account gone.
- Entry deletion commits, then deletes vectors. After upserting, the ids are
  checked again and vectors whose memories have gone are deleted here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Query, Session

from thoughtpins.config import config
from thoughtpins.db import Memory, User
from thoughtpins.store import get_session
from thoughtpins.tenancy import tenant_context
from thoughtpins.usage import UsageBudgetExceeded
from thoughtpins.users import lock_active_user_for_write

_REPAIR_PAGE_SIZE = 128
_REPAIR_TIME_BUDGET_SECONDS = 600.0


@dataclass
class VectorRepairStats:
    scanned: int = 0
    missing: int = 0
    indexed: int = 0
    failed_accounts: int = 0
    complete: bool = True


def vector_metadata(memory: Memory) -> dict[str, Any]:
    return {
        "user_id": memory.user_id,
        "raw_entry_id": memory.raw_entry_id,
        "memory_type": memory.memory_type,
        "local_date": memory.local_date.isoformat() if memory.local_date else None,
        "source_provenance": memory.source_provenance,
    }


def schedule_entry_vector_index(user_id: str, entry_id: str) -> None:
    """Hand a committed entry to the indexer. Never raises into the save."""
    if not config.VECTOR_INDEX_ON_INGEST:
        return
    if config.INGESTION_QUEUE_BACKEND != "celery":
        # Local development: the thread backend already runs saves off the request.
        index_entry_vectors(entry_id, user_id)
        return
    try:
        from thoughtpins.worker import enqueue_entry_vector_index

        enqueue_entry_vector_index(entry_id, user_id)
    except Exception as exc:
        logger.warning("Vector indexing for entry {} left to the repair sweep ({})", entry_id, type(exc).__name__)


def index_entry_vectors(entry_id: str, user_id: str) -> int:
    """Index one entry's live memories and return how many were written. Never raises."""
    session = get_session()
    try:
        with tenant_context(user_id):
            memories = _live_memories(session, user_id).filter(Memory.raw_entry_id == entry_id).all()
            return _index_memories(session, user_id, memories)
    except UsageBudgetExceeded:
        logger.info("Vector indexing for entry {} paused by the usage budget", entry_id)
    except Exception as exc:
        logger.warning(
            "Vector indexing failed for entry {} ({}); the repair sweep will retry", entry_id, type(exc).__name__
        )
    finally:
        session.close()
    return 0


def repair_entry_vectors(
    *,
    lookback_hours: int | None,
    time_budget_seconds: float = _REPAIR_TIME_BUDGET_SECONDS,
) -> VectorRepairStats:
    """Index live memories that have no vector; ``None`` looks back over all of them."""
    from thoughtpins.memory.vector_store import get_vector_store

    stats = VectorRepairStats()
    store = get_vector_store()
    since = None if lookback_hours is None else _utcnow() - timedelta(hours=lookback_hours)
    deadline = time.monotonic() + time_budget_seconds
    for user_id in _active_user_ids():
        if time.monotonic() >= deadline:
            stats.complete = False
            break
        try:
            _repair_account(store, user_id, since=since, deadline=deadline, stats=stats)
        except UsageBudgetExceeded:
            logger.info("Vector repair skipped one account paused by the usage budget")
        except Exception as exc:
            stats.failed_accounts += 1
            logger.warning("Vector repair skipped one account ({})", type(exc).__name__)
    logger.info(
        "Vector repair: scanned={}, missing={}, indexed={}, failed_accounts={}, complete={}",
        stats.scanned,
        stats.missing,
        stats.indexed,
        stats.failed_accounts,
        stats.complete,
    )
    return stats


def _repair_account(
    store: Any,
    user_id: str,
    *,
    since: datetime | None,
    deadline: float,
    stats: VectorRepairStats,
) -> None:
    session = get_session()
    try:
        with tenant_context(user_id):
            query = _live_memories(session, user_id)
            if since is not None:
                query = query.filter(Memory.created_at_utc >= since)
            query = query.order_by(Memory.created_at_utc.asc(), Memory.id.asc())
            offset = 0
            while True:
                if time.monotonic() >= deadline:
                    stats.complete = False
                    return
                page = query.offset(offset).limit(_REPAIR_PAGE_SIZE).all()
                if not page:
                    return
                offset += len(page)
                stats.scanned += len(page)
                missing = set(store.missing_ids([memory.id for memory in page]))
                if missing:
                    stats.missing += len(missing)
                    stats.indexed += _index_memories(
                        session, user_id, [memory for memory in page if memory.id in missing]
                    )
    finally:
        session.close()


def _index_memories(session: Session, user_id: str, memories: list[Memory]) -> int:
    from thoughtpins.memory.vector_store import get_vector_store

    rows = [(memory.id, memory.text, vector_metadata(memory)) for memory in memories if memory.text]
    # End the read before the provider call, so no lock is held across it.
    session.rollback()
    if not rows:
        return 0
    store = get_vector_store()
    vectors = store.embed_documents([text for _, text, _ in rows])
    try:
        lock_active_user_for_write(session, user_id)
    except ValueError:
        # The account is being deleted, and its vectors are deleted with it.
        session.rollback()
        return 0
    live = _live_ids(session, user_id, [memory_id for memory_id, _, _ in rows])
    kept = [(row, vector) for row, vector in zip(rows, vectors, strict=True) if row[0] in live]
    if kept:
        store.add(
            [row[0] for row, _ in kept],
            [row[1] for row, _ in kept],
            [row[2] for row, _ in kept],
            vectors=[vector for _, vector in kept],
        )
    # Only now release the share lock that holds account deletion off.
    session.commit()
    written = [row[0] for row, _ in kept]
    if not written:
        return 0
    still_live = _live_ids(session, user_id, written)
    session.rollback()
    vanished = [memory_id for memory_id in written if memory_id not in still_live]
    if vanished:
        store.delete(vanished)
    return len(written) - len(vanished)


def _live_memories(session: Session, user_id: str) -> Query:
    return session.query(Memory).filter(Memory.user_id == user_id, Memory.valid_to.is_(None))


def _live_ids(session: Session, user_id: str, ids: list[str]) -> set[str]:
    rows = session.query(Memory.id).filter(Memory.user_id == user_id, Memory.valid_to.is_(None), Memory.id.in_(ids))
    return {row[0] for row in rows.all()}


def _active_user_ids() -> list[str]:
    session = get_session()
    try:
        rows = session.query(User.id).filter(User.is_active == True).order_by(User.created_at_utc.asc()).all()
        return [row[0] for row in rows]
    finally:
        session.close()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
