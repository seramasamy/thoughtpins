"""Best-effort startup repair for interrupted local ingestion work."""

from __future__ import annotations

import datetime
import json
from typing import Any

from loguru import logger
from sqlalchemy import func

from thoughtpins.db import Entity, Memory, RawEntry, Relationship
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.store import get_session


def recover_orphaned_entries() -> None:
    """Retry stale entries and prune old entities that never gained evidence."""

    session = get_session()
    recovered = 0
    retried = 0
    cleaned = 0

    try:
        orphans = session.query(RawEntry).filter(RawEntry.processed_status == "processing").all()
        for entry in orphans:
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            age = now - entry.created_at_utc
            if age.total_seconds() < 3600:
                continue
            entry.processed_status = "error"
            entry.processing_error = "Orphaned: process stopped mid-extraction."
            recovered += 1

        if recovered:
            session.flush()
        failed = session.query(RawEntry).filter(RawEntry.processed_status == "error").all()
        for entry in failed:
            retry_data: dict[str, Any] = {}
            if entry.processing_error and entry.processing_error.startswith("{"):
                try:
                    retry_data = json.loads(entry.processing_error)
                except (TypeError, ValueError):
                    retry_data = {}
            attempts = retry_data.get("retries", 0)
            if attempts >= 3:
                continue

            retry_data["retries"] = attempts + 1
            entry.processing_error = json.dumps(retry_data)
            try:
                process_message(
                    session,
                    entry.raw_text,
                    user_id=entry.user_id,
                    source=entry.source or "recovery",
                    telegram_message_id=entry.telegram_message_id or "",
                    telegram_chat_id=entry.telegram_chat_id or "",
                    author_user_id=entry.author_user_id or "",
                    is_private=entry.is_private,
                )
                retried += 1
            except Exception as exc:
                logger.warning("Retry failed for {}: {}", entry.id, type(exc).__name__)
                retry_data["last_error_type"] = type(exc).__name__
                entry.processing_error = json.dumps(retry_data)

        cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=24)
        entities = (
            session.query(Entity)
            .filter(
                Entity.canonical_name != "User",
                Entity.created_at_utc < cutoff,
            )
            .all()
        )
        for entity in entities:
            memory_count = (
                session.query(func.count(Memory.id))
                .filter((Memory.subject_entity_id == entity.id) | (Memory.object_entity_id == entity.id))
                .scalar()
            )
            relationship_count = (
                session.query(func.count(Relationship.id))
                .filter((Relationship.source_entity_id == entity.id) | (Relationship.target_entity_id == entity.id))
                .scalar()
            )
            if memory_count == 0 and relationship_count == 0:
                session.delete(entity)
                cleaned += 1

        session.commit()
        if recovered or retried or cleaned:
            logger.info(
                "Startup recovery: {} orphaned, {} retried, {} orphan entities cleaned",
                recovered,
                retried,
                cleaned,
            )
    except Exception as exc:
        logger.error("Recovery check failed: {}", type(exc).__name__)
        session.rollback()
    finally:
        session.close()
