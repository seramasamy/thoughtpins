"""Rebuild the derived vector index from relational memories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.db import Memory, RawEntry
from thoughtpins.memory.vector_store import get_vector_store
from thoughtpins.store import get_session


@dataclass
class ReindexStats:
    scanned: int = 0
    indexed: int = 0
    batches: int = 0
    deleted_existing: int = 0
    reset_index: bool = False
    user_id: str | None = None
    include_private: bool = True


def reindex_vectors(
    *,
    session: Session | None = None,
    user_id: str | None = None,
    include_private: bool = True,
    batch_size: int = 128,
    reset: bool = True,
    limit: int | None = None,
) -> ReindexStats:
    """Reindex memories into the configured vector store.

    A global reindex can safely reset the whole derived vector store. A scoped
    user reindex deletes current vector rows for that user's live memory IDs
    before re-adding them, avoiding accidental cross-tenant index deletion.
    Database filtering remains the source of truth for tenant isolation.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive when provided")

    owned_session = session is None
    if session is None:
        session = get_session()

    stats = ReindexStats(
        user_id=user_id,
        include_private=include_private,
    )
    vector_store = get_vector_store()

    try:
        query = _memory_query(session, user_id=user_id, include_private=include_private)
        if limit:
            query = query.limit(limit)
        memories = query.all()
        stats.scanned = len(memories)

        ids = [memory.id for memory in memories]
        if reset and user_id is None:
            vector_store.reset()
            stats.reset_index = True
        elif reset and ids:
            vector_store.delete(ids)
            stats.deleted_existing = len(ids)

        for batch in _batched(memories, batch_size):
            batch_ids = [memory.id for memory in batch]
            texts = [memory.text for memory in batch]
            metadata = [
                {
                    "user_id": memory.user_id,
                    "raw_entry_id": memory.raw_entry_id,
                    "memory_type": memory.memory_type,
                    "local_date": memory.local_date.isoformat() if memory.local_date else None,
                    "source_provenance": memory.source_provenance,
                }
                for memory in batch
            ]
            vector_store.add(batch_ids, texts, metadata)
            stats.indexed += len(batch)
            stats.batches += 1

        logger.info(
            "Vector reindex complete: scanned={}, indexed={}, batches={}, reset={}, user_id={}",
            stats.scanned,
            stats.indexed,
            stats.batches,
            stats.reset_index,
            user_id or "all",
        )
        return stats
    finally:
        if owned_session:
            session.close()


def _memory_query(session: Session, *, user_id: str | None, include_private: bool):
    query = (
        session.query(Memory)
        .filter(Memory.valid_to.is_(None))
        .order_by(
            Memory.local_date.asc(),
            Memory.created_at_utc.asc(),
            Memory.id.asc(),
        )
    )
    if user_id:
        query = query.filter(Memory.user_id == user_id)
    if not include_private:
        query = query.join(RawEntry, Memory.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _batched(items: list[Memory], batch_size: int) -> Iterable[list[Memory]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]
