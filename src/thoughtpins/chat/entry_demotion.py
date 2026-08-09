"""Turn a processed journal entry back into a plain chat message.

Demoting an entry deletes everything extraction derived from it and revives the
memories it had superseded, so recall stops answering from a version of the past
the user has withdrawn. The caller is responsible for refreshing the vector index
with the ids this returns.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from thoughtpins.chat.message_memory import CHAT_SOURCE, CHAT_STATUS
from thoughtpins.db import Memory, RawEntry
from thoughtpins.memory.context_scope import scope_user

__all__ = ["demote_entry_to_chat"]

_DERIVED_ATTRS = (
    "entity_mentions",
    "relationships_ref",
    "action_items",
    "expenses",
    "document_sources",
    "events",
    "memories",
)


def demote_entry_to_chat(
    session: Session,
    entry: RawEntry,
    *,
    user_id: str,
) -> tuple[list[str], list[Memory]]:
    memory_ids = [memory.id for memory in entry.memories]
    superseded_ids = [memory.supersedes_memory_id for memory in entry.memories if memory.supersedes_memory_id]
    restored_memories: list[Memory] = []
    if superseded_ids:
        restored_memories = (
            scope_user(session.query(Memory), Memory, user_id).filter(Memory.id.in_(superseded_ids)).all()
        )
        for memory in restored_memories:
            memory.valid_to = None

    for attr in _DERIVED_ATTRS:
        for item in list(getattr(entry, attr, []) or []):
            session.delete(item)

    entry.source = CHAT_SOURCE
    entry.processed_status = CHAT_STATUS
    entry.sensitivity = "personal"
    entry.processing_error = None
    return memory_ids, restored_memories
