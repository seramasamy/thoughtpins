"""Vector-store repair after an entry's memories are removed or restored.

Rewriting an entry deletes the memories it produced and may bring back the ones
they superseded. The vector index has to be told about both halves, or recall
keeps answering from text that no longer exists.
"""

from __future__ import annotations

from loguru import logger

from thoughtpins.db import Memory


def refresh_vectors_after_removed_memories(
    memory_ids: list[str],
    restored_memories: list[Memory],
    entry_id: str,
) -> None:
    """Drop vectors for removed memories and re-add any that were restored."""
    try:
        from thoughtpins.memory.vector_store import get_vector_store

        vector_store = get_vector_store()
        if memory_ids:
            vector_store.delete(memory_ids)
        if restored_memories:
            vector_store.add(
                [memory.id for memory in restored_memories],
                [memory.text for memory in restored_memories],
                [{"user_id": memory.user_id} for memory in restored_memories],
            )
    except Exception as exc:
        logger.warning("Vector refresh failed after entry rewrite {}: {}", entry_id, exc)
