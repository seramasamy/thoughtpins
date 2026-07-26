"""Shared identity rules for conversational memory records."""

from __future__ import annotations

from thoughtpins.db import RawEntry

CHAT_SOURCE = "telegram_chat"
CHAT_STATUS = "conversation"


def is_chat_memory_entry(entry: RawEntry) -> bool:
    """Return whether a raw record represents conversation rather than a journal save."""

    return entry.source == CHAT_SOURCE or entry.processed_status == CHAT_STATUS
