"""Correction storage and supersession logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import Entity, Memory, RawEntry
from thoughtpins.utils import hash_text


@dataclass
class ParsedCorrection:
    text: str
    correct: str = ""
    wrong: str = ""
    context: str = ""


@dataclass
class CorrectionResult:
    raw_entry_id: str
    fixes: list[str] = field(default_factory=list)
    superseded_memory_ids: list[str] = field(default_factory=list)
    correction_memory_ids: list[str] = field(default_factory=list)
    updated_entity_ids: list[str] = field(default_factory=list)


def store_and_apply_correction(
    session: Session,
    text: str,
    *,
    user_id: str,
    source: str = "telegram",
    telegram_message_id: str = "",
    telegram_chat_id: str = "",
    author_user_id: str = "",
) -> CorrectionResult:
    raw_entry = _store_correction_raw_entry(
        session,
        text,
        user_id=user_id,
        source=source,
        telegram_message_id=telegram_message_id,
        telegram_chat_id=telegram_chat_id,
        author_user_id=author_user_id,
    )
    result = apply_correction(session, text, user_id=user_id, raw_entry=raw_entry)
    session.commit()
    _refresh_correction_vectors(session, result)
    return result


def apply_correction(
    session: Session,
    text: str,
    *,
    user_id: str,
    raw_entry: RawEntry,
) -> CorrectionResult:
    parsed = parse_correction(text)
    result = CorrectionResult(raw_entry_id=raw_entry.id)
    now = _utcnow()

    matched_memories: list[Memory] = []
    if parsed.wrong:
        matched_memories = _find_memories_to_supersede(session, parsed, user_id=user_id)
        for memory in matched_memories:
            memory.valid_to = now
            result.superseded_memory_ids.append(memory.id)

    updated_entities = _apply_entity_replacement(session, parsed, user_id=user_id)
    result.updated_entity_ids.extend(entity.id for entity in updated_entities)
    for entity in updated_entities:
        result.fixes.append(f"Updated entity '{entity.canonical_name}'")

    correction_text = _correction_memory_text(parsed)
    if matched_memories:
        for memory in matched_memories:
            correction_memory = _new_correction_memory(
                raw_entry,
                correction_text,
                parsed,
                supersedes_memory_id=memory.id,
            )
            session.add(correction_memory)
            session.flush()
            result.correction_memory_ids.append(correction_memory.id)
    else:
        correction_memory = _new_correction_memory(raw_entry, correction_text, parsed)
        session.add(correction_memory)
        session.flush()
        result.correction_memory_ids.append(correction_memory.id)

    if matched_memories:
        result.fixes.append(f"Superseded {len(matched_memories)} old memory record(s)")
    else:
        result.fixes.append("Stored correction as a new memory")
    return result


def parse_correction(text: str) -> ParsedCorrection:
    clean = " ".join((text or "").strip().split())
    lowered = clean.lower()
    prefix_removed = re.sub(
        r"^(actually|correction[:,]?|i meant[:,]?|that's wrong[:,]?|change that[:,]?)\s+", "", clean, flags=re.I
    )

    patterns = [
        r"^(?P<context>.+?)\s+(?:is|was|are|were)\s+(?P<correct>[^,.;]+),\s*not\s+(?P<wrong>.+)$",
        r"^(?P<context>.+?)\s+not\s+(?P<wrong>[^,.;]+),\s*(?:it'?s|is|was|should be)\s+(?P<correct>.+)$",
        r"^(?P<wrong>.+?)\s*(?:->|=>|=)\s*(?P<correct>.+)$",
        r"^(?P<context>.+?)\s+(?:is actually|was actually|should be|should've been)\s+(?P<correct>.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, prefix_removed, flags=re.I)
        if not match:
            continue
        groups = {key: _clean_piece(value) for key, value in match.groupdict(default="").items()}
        return ParsedCorrection(
            text=clean,
            correct=groups.get("correct", ""),
            wrong=groups.get("wrong", ""),
            context=groups.get("context", ""),
        )

    if lowered.startswith(("actually", "correction", "i meant", "that's wrong", "change that")):
        return ParsedCorrection(text=clean, context=prefix_removed)
    return ParsedCorrection(text=clean)


def _store_correction_raw_entry(
    session: Session,
    text: str,
    *,
    user_id: str,
    source: str,
    telegram_message_id: str,
    telegram_chat_id: str,
    author_user_id: str,
) -> RawEntry:
    tz = ZoneInfo(config.LOCAL_TIMEZONE)
    now_utc = _utcnow()
    now_local = datetime.now(tz)
    raw_entry = RawEntry(
        user_id=user_id,
        created_at_utc=now_utc,
        local_date=now_local.date(),
        local_time=now_local.strftime("%H:%M"),
        source=source,
        telegram_message_id=str(telegram_message_id) if telegram_message_id else "",
        telegram_chat_id=str(telegram_chat_id) if telegram_chat_id else "",
        author_user_id=str(author_user_id) if author_user_id else "",
        raw_text=text,
        content_hash=hash_text(text),
        is_private=False,
        sensitivity="personal",
        processed_status="completed",
    )
    session.add(raw_entry)
    session.flush()
    return raw_entry


def _find_memories_to_supersede(session: Session, parsed: ParsedCorrection, *, user_id: str) -> list[Memory]:
    wrong = parsed.wrong.strip()
    if len(wrong) < 2:
        return []
    candidates = (
        session.query(Memory)
        .filter(
            Memory.user_id == user_id,
            Memory.valid_to.is_(None),
            Memory.text.ilike(f"%{wrong}%"),
        )
        .order_by(Memory.local_date.desc(), Memory.created_at_utc.desc())
        .limit(50)
        .all()
    )
    context_tokens = _tokens(parsed.context)
    if not context_tokens:
        return candidates[:10]
    scored = [(len(context_tokens & _tokens(memory.text)), memory) for memory in candidates]
    matched = [memory for score, memory in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    return matched[:10] or candidates[:5]


def _apply_entity_replacement(session: Session, parsed: ParsedCorrection, *, user_id: str) -> list[Entity]:
    if not parsed.wrong or not parsed.correct:
        return []
    wrong_norm = _normal(parsed.wrong)
    correct = parsed.correct.strip()
    if len(correct) < 2:
        return []
    entities = (
        session.query(Entity).filter(Entity.user_id == user_id).order_by(Entity.created_at_utc.desc()).limit(500).all()
    )
    updated: list[Entity] = []
    for entity in entities:
        aliases = list(entity.aliases_json or [])
        names = [entity.canonical_name, *aliases]
        if not any(_normal(name) == wrong_norm for name in names):
            continue
        old_name = entity.canonical_name
        if _normal(old_name) == wrong_norm:
            entity.canonical_name = correct
        if old_name not in aliases and _normal(old_name) != _normal(correct):
            aliases.append(old_name)
        if parsed.wrong not in aliases and _normal(parsed.wrong) != _normal(correct):
            aliases.append(parsed.wrong)
        entity.aliases_json = aliases
        updated.append(entity)
    return updated


def _new_correction_memory(
    raw_entry: RawEntry,
    text: str,
    parsed: ParsedCorrection,
    *,
    supersedes_memory_id: str | None = None,
) -> Memory:
    return Memory(
        user_id=raw_entry.user_id,
        raw_entry_id=raw_entry.id,
        memory_type="correction",
        text=text,
        structured_json={
            "correction": True,
            "wrong": parsed.wrong,
            "correct": parsed.correct,
            "context": parsed.context,
        },
        local_date=raw_entry.local_date,
        sensitivity=raw_entry.sensitivity,
        confidence="observed_by_user",
        source_provenance=f"raw_entry:{raw_entry.id}",
        supersedes_memory_id=supersedes_memory_id,
        created_at_utc=raw_entry.created_at_utc,
    )


def _correction_memory_text(parsed: ParsedCorrection) -> str:
    if parsed.correct and parsed.wrong and parsed.context:
        return f"Correction: {parsed.context} is {parsed.correct}, not {parsed.wrong}."
    if parsed.correct and parsed.wrong:
        return f"Correction: replace {parsed.wrong} with {parsed.correct}."
    if parsed.correct and parsed.context:
        return f"Correction: {parsed.context} is {parsed.correct}."
    return f"Correction: {parsed.text}"


def _refresh_correction_vectors(session: Session, result: CorrectionResult) -> None:
    try:
        from thoughtpins.memory.vector_store import get_vector_store

        vector_store = get_vector_store()
        if result.superseded_memory_ids:
            vector_store.delete(result.superseded_memory_ids)
        correction_memories = (
            session.query(Memory)
            .filter(Memory.id.in_(result.correction_memory_ids))
            .order_by(Memory.created_at_utc.asc())
            .all()
        )
        if correction_memories:
            vector_store.add(
                [memory.id for memory in correction_memories],
                [memory.text for memory in correction_memories],
                [{"user_id": memory.user_id} for memory in correction_memories],
            )
    except Exception as exc:
        logger.warning("Correction vector refresh failed: {}", exc)


def _clean_piece(value: str) -> str:
    return value.strip().strip("'\"` .,;:")


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", (text or "").lower())
        if token not in {"the", "and", "not", "but", "actually", "correction", "is", "was", "are", "were"}
    }


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", maybe_decrypt_text(text or "").lower()).strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
