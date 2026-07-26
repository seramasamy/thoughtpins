"""Main ingestion pipeline -- orchestrate classification, extraction, storage, and export."""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.db import RawEntry
from thoughtpins.ingestion.classify import classify_message
from thoughtpins.ingestion.extraction import extract_from_entry
from thoughtpins.ingestion.postprocess import (  # noqa: F401
    _auto_link_entities_to_memories,
    _normalize_sensitivity,
)
from thoughtpins.ingestion.service import (
    IngestionDependencies,
    IngestionOptions,
    ingest_message,
)
from thoughtpins.ingestion.storage import store_extraction as _store_extraction  # noqa: F401
from thoughtpins.users import get_or_create_default_user, get_or_create_user_for_telegram, lock_active_user_for_write


def _resolve_owner_user_id(
    session: Session,
    *,
    user_id: str | None = None,
    telegram_chat_id: str = "",
) -> str:
    """Resolve the tenant owner for an incoming entry."""
    if user_id:
        return lock_active_user_for_write(session, user_id).id

    if telegram_chat_id and telegram_chat_id != "api":
        user = get_or_create_user_for_telegram(telegram_chat_id, session=session)
        return user.id

    return get_or_create_default_user(session=session).id


def process_message(
    session: Session,
    text: str,
    *,
    user_id: str | None = None,
    source: str = "telegram",
    telegram_message_id: str = "",
    telegram_chat_id: str = "",
    author_user_id: str = "",
    is_private: bool = False,
    occurred_at_utc: datetime | None = None,
    force_journal: bool = False,
    dedup_key: str = "",
    user_importance: int | None = None,
) -> dict:
    """Classify and persist one message through the transactional ingestion service."""
    owner_user_id = _resolve_owner_user_id(
        session,
        user_id=user_id,
        telegram_chat_id=telegram_chat_id,
    )
    return ingest_message(
        session,
        text,
        owner_user_id=owner_user_id,
        options=IngestionOptions(
            source=source,
            telegram_message_id=str(telegram_message_id) if telegram_message_id else "",
            telegram_chat_id=str(telegram_chat_id) if telegram_chat_id else "",
            author_user_id=str(author_user_id) if author_user_id else "",
            is_private=is_private,
            occurred_at_utc=occurred_at_utc,
            force_journal=force_journal,
            dedup_key=dedup_key,
            user_importance=user_importance,
        ),
        dependencies=IngestionDependencies(
            classify=classify_message,
            extract=extract_from_entry,
            mirror=_mirror_raw_entry_to_graph_backend,
        ),
    )


def _mirror_raw_entry_to_graph_backend(session: Session, raw_entry: RawEntry, text: str) -> None:
    try:
        from thoughtpins.memory.graph_backend import GraphEpisode, add_episode_to_graph_backend

        add_episode_to_graph_backend(
            session,
            GraphEpisode(
                user_id=raw_entry.user_id,
                episode_id=raw_entry.id,
                name=f"journal_entry_{raw_entry.id}",
                body=text,
                source="text",
                source_description="Thought Pins journal entry",
                reference_time=raw_entry.created_at_utc,
                metadata={
                    "raw_entry_id": raw_entry.id,
                    "source": raw_entry.source,
                    "user_importance": raw_entry.user_importance,
                },
            ),
        )
    except Exception as exc:
        logger.debug("Graph backend mirror skipped for raw entry {}: {}", raw_entry.id, str(exc)[:160])
