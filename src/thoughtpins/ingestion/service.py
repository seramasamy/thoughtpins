"""Transactional orchestration for one routed journal message."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import encrypt_for_storage
from thoughtpins.db import RawEntry
from thoughtpins.importance import normalize_user_importance
from thoughtpins.ingestion.postprocess import (
    _auto_link_entities_to_memories,
    _normalize_sensitivity,
    _pick_max_sensitivity,
)
from thoughtpins.ingestion.storage import store_extraction
from thoughtpins.llm import ExtractionResult
from thoughtpins.memory.salience_store import update_salience_for_entry
from thoughtpins.users import lock_active_user_for_write
from thoughtpins.utils import hash_text

ClassifyMessage = Callable[[str], dict[str, Any]]
ExtractMessage = Callable[[str, str], ExtractionResult]
MirrorEntry = Callable[[Session, RawEntry, str], None]

_EXPORT_LOCK = Lock()
_last_export_time = 0.0


@dataclass(frozen=True)
class IngestionOptions:
    source: str = "telegram"
    telegram_message_id: str = ""
    telegram_chat_id: str = ""
    author_user_id: str = ""
    is_private: bool = False
    occurred_at_utc: datetime | None = None
    force_journal: bool = False
    dedup_key: str = ""
    user_importance: int | None = None


@dataclass(frozen=True)
class IngestionDependencies:
    classify: ClassifyMessage
    extract: ExtractMessage
    mirror: MirrorEntry


@dataclass(frozen=True)
class _MessageClock:
    utc: datetime
    local: datetime
    local_date: date


class MessageIngestor:
    def __init__(
        self,
        session: Session,
        text: str,
        *,
        owner_user_id: str,
        options: IngestionOptions,
        dependencies: IngestionDependencies,
    ) -> None:
        self.session = session
        self.text = text
        self.user_id = owner_user_id
        self.options = options
        self.dependencies = dependencies
        self.clock = _message_clock(options.occurred_at_utc)
        hash_input = f"{options.dedup_key}\n{text}" if options.dedup_key else text
        self.content_hash = hash_text(hash_input)
        self.importance = normalize_user_importance(options.user_importance)

    def run(self) -> dict[str, Any]:
        duplicate = self._duplicate_response()
        if duplicate is not None:
            return duplicate
        routed = self._route_without_storage()
        if routed is not None:
            return routed
        raw_entry = self._store_raw_entry()
        private = self._private_response(raw_entry)
        if private is not None:
            return private
        extraction, failure = self._extract(raw_entry)
        if failure is not None or extraction is None:
            return failure or self._error_response(raw_entry, "ExtractionUnavailable")
        return self._persist(raw_entry, extraction)

    def _duplicate_response(self) -> dict[str, Any] | None:
        existing = (
            self.session.query(RawEntry)
            .filter(
                RawEntry.user_id == self.user_id,
                RawEntry.content_hash == self.content_hash,
                RawEntry.created_at_utc >= self.clock.utc - timedelta(hours=24),
            )
            .first()
        )
        if existing is None:
            return None
        if self.importance is not None and existing.user_importance != self.importance:
            existing.user_importance = self.importance
            existing.importance_source = "ingest"
            existing.importance_updated_at = self.clock.utc
            self.session.commit()
        logger.info("Duplicate entry detected (hash={}, within 24h), skipping", self.content_hash)
        return {
            "type": "duplicate",
            "entry_id": existing.id,
            "message": "Already stored recently.",
            "user_importance": existing.user_importance,
        }

    def _route_without_storage(self) -> dict[str, Any] | None:
        if self.options.is_private:
            return None
        if self.options.force_journal:
            return None
        classification = self.dependencies.classify(self.text)
        message_type = str(classification.get("type", "journal_entry"))
        intent = str(classification.get("intent", ""))
        if message_type == "mixed":
            return None
        if message_type in {"command", "correction"}:
            return {"type": message_type, "text": self.text}
        if message_type in {"query", "report_request", "document_link", "document_text", "ambiguous"}:
            return {"type": message_type, "intent": intent, "text": self.text}
        return None

    def _store_raw_entry(self) -> RawEntry:
        stored_text = self._stored_text()
        raw_entry = RawEntry(
            user_id=self.user_id,
            created_at_utc=self.clock.utc,
            local_date=self.clock.local_date,
            local_time=self.clock.local.strftime("%H:%M"),
            source=self.options.source,
            telegram_message_id=str(self.options.telegram_message_id),
            telegram_chat_id=str(self.options.telegram_chat_id),
            author_user_id=str(self.options.author_user_id),
            raw_text=stored_text,
            content_hash=self.content_hash,
            is_private=self.options.is_private,
            sensitivity="private" if self.options.is_private else "personal",
            processed_status="processing",
            user_importance=self.importance,
            importance_source="ingest" if self.importance is not None else None,
            importance_updated_at=self.clock.utc if self.importance is not None else None,
        )
        self.session.add(raw_entry)
        self.session.flush()
        logger.info("Stored raw entry {}", raw_entry.id)
        self.session.commit()
        return raw_entry

    def _stored_text(self) -> str:
        if not self.options.is_private:
            return self.text
        encrypted = encrypt_for_storage(self.text)
        if encrypted:
            return encrypted
        if config.is_production():
            raise RuntimeError("DATA_ENCRYPTION_KEY is required for private entries in production.")
        logger.warning("DATA_ENCRYPTION_KEY missing; private entry stored unencrypted in local mode")
        return self.text

    def _private_response(self, raw_entry: RawEntry) -> dict[str, Any] | None:
        if not self.options.is_private or config.PRIVATE_ALLOW_LLM:
            return None
        raw_entry.processed_status = "stored_private"
        lock_active_user_for_write(self.session, self.user_id)
        self.session.commit()
        return {
            "type": "private_stored",
            "entry_id": raw_entry.id,
            "user_importance": raw_entry.user_importance,
            "message": "Private entry stored (not processed by LLM).",
        }

    def _extract(self, raw_entry: RawEntry) -> tuple[ExtractionResult | None, dict[str, Any] | None]:
        local_datetime = self.clock.local.strftime("%Y-%m-%d %H:%M %Z")
        try:
            return self.dependencies.extract(self.text, local_datetime), None
        except Exception as exc:
            retryable = _is_retryable_provider_failure(exc)
            raw_entry.processed_status = "queued" if retryable else "error"
            if retryable:
                raw_entry.processing_error = f"Provider unavailable - queued for retry. {type(exc).__name__}"
                logger.warning("Provider outage detected, entry {} queued", raw_entry.id)
            else:
                raw_entry.processing_error = f"Extraction failed: {type(exc).__name__}"
            lock_active_user_for_write(self.session, self.user_id)
            self.session.commit()
            return None, {
                "type": "queued" if retryable else "error",
                "entry_id": raw_entry.id,
                "user_importance": raw_entry.user_importance,
                "error": "The memory processor is temporarily unavailable."
                if retryable
                else "Memory extraction failed.",
            }

    def _persist(self, raw_entry: RawEntry, extraction: ExtractionResult) -> dict[str, Any]:
        try:
            _normalize_sensitivity(extraction)
            from thoughtpins.ingestion.extraction import correct_entity_types

            extraction = correct_entity_types(extraction, self.text)
            stats = store_extraction(
                self.session,
                raw_entry,
                extraction,
                self.clock.local_date,
                raw_text=self.text,
            )
            _auto_link_entities_to_memories(self.session, raw_entry.id)
            self._update_salience(raw_entry, extraction, stats)
            raw_entry.processed_status = "completed"
            raw_entry.sensitivity = _pick_max_sensitivity(extraction.sensitivity_tags)
            self.dependencies.mirror(self.session, raw_entry, self.text)
            lock_active_user_for_write(self.session, self.user_id)
            self.session.commit()
        except Exception as exc:
            logger.exception("Extraction persistence failed for {} ({})", raw_entry.id, type(exc).__name__)
            self.session.rollback()
            current = (
                self.session.query(RawEntry).filter(RawEntry.id == raw_entry.id, RawEntry.user_id == self.user_id).one()
            )
            current.processed_status = "error"
            current.processing_error = f"Persistence failed: {type(exc).__name__}"
            lock_active_user_for_write(self.session, self.user_id)
            self.session.commit()
            return self._error_response(current, type(exc).__name__)
        _maybe_export_vault(self.session, self.user_id, raw_entry.id)
        return {
            "type": "journal_stored",
            "entry_id": raw_entry.id,
            "user_importance": raw_entry.user_importance,
            "stats": stats,
        }

    def _update_salience(
        self,
        raw_entry: RawEntry,
        extraction: ExtractionResult,
        stats: dict[str, Any],
    ) -> None:
        try:
            salience = update_salience_for_entry(
                self.session,
                raw_entry,
                extraction,
                stats,
                source_text=self.text,
            )
            stats["contextual_salience"] = salience.score
            stats["salience_tier"] = salience.tier
        except Exception as exc:
            logger.warning("Contextual salience update skipped for {}: {}", raw_entry.id, type(exc).__name__)

    @staticmethod
    def _error_response(raw_entry: RawEntry, error_type: str) -> dict[str, Any]:
        return {
            "type": "error",
            "entry_id": raw_entry.id,
            "user_importance": raw_entry.user_importance,
            "error": f"Memory persistence failed ({error_type}).",
        }


def ingest_message(
    session: Session,
    text: str,
    *,
    owner_user_id: str,
    options: IngestionOptions,
    dependencies: IngestionDependencies,
) -> dict[str, Any]:
    return MessageIngestor(
        session,
        text,
        owner_user_id=owner_user_id,
        options=options,
        dependencies=dependencies,
    ).run()


def _message_clock(occurred_at_utc: datetime | None) -> _MessageClock:
    if occurred_at_utc is None:
        utc = datetime.now(timezone.utc).replace(tzinfo=None)
    elif occurred_at_utc.tzinfo is not None:
        utc = occurred_at_utc.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        utc = occurred_at_utc
    local = utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(config.LOCAL_TIMEZONE))
    return _MessageClock(utc=utc, local=local, local_date=local.date())


def _is_retryable_provider_failure(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status in {408, 409, 425, 429} or status >= 500
    text = str(error).lower()
    return any(
        marker in text
        for marker in ("connection", "timeout", "timed out", "refused", "unreachable", "rate limit", "overloaded")
    )


def _maybe_export_vault(session: Session, user_id: str, entry_id: str) -> None:
    global _last_export_time
    now = time.time()
    with _EXPORT_LOCK:
        if now - _last_export_time <= 600:
            return
        try:
            from thoughtpins.obsidian.exporter import ObsidianExporter

            ObsidianExporter(session, user_id=user_id).export_all()
            _last_export_time = now
            logger.debug("Auto-exported Obsidian vault after entry {}", entry_id)
        except Exception as exc:
            logger.warning("Auto-export failed (non-critical): {}", type(exc).__name__)
