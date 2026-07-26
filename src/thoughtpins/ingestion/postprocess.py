"""Deterministic normalization and deduplication after LLM extraction."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from datetime import time as datetime_time

from loguru import logger

from thoughtpins.utils import parse_relative_date


def _parse_action_due_at(value: str | None, local_date: date) -> datetime | None:
    """Parse LLM due_at text into a stable local datetime."""
    if not value:
        return None

    text = value.strip()
    if not text or text.lower() in {"none", "null", "n/a"}:
        return None

    parsed_relative = parse_relative_date(text, local_date)
    inferred = parsed_relative.get("inferred_start")
    if inferred:
        try:
            return datetime.combine(date.fromisoformat(inferred), _extract_time_hint(text) or datetime_time(hour=9))
        except ValueError:
            return None

    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime.combine(date.fromisoformat(text), datetime_time(hour=9))
        except ValueError:
            return None

    try:
        parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed_dt.tzinfo:
            return parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed_dt
    except ValueError:
        return None


def _infer_action_due_at_from_text(description: str, raw_text: str, local_date: date) -> datetime | None:
    """Recover common reminder due dates when extraction omits due_at."""
    combined = f"{description} {raw_text}".lower()
    time_hint = _extract_time_hint(combined)
    phrase_defaults = {
        "tomorrow": 9,
        "today": 17,
        "tonight": 20,
        "next week": 9,
        "next month": 9,
    }
    for phrase, hour in phrase_defaults.items():
        if phrase not in combined:
            continue
        parsed = parse_relative_date(phrase, local_date)
        inferred = parsed.get("inferred_start")
        if not inferred:
            continue
        try:
            return datetime.combine(date.fromisoformat(inferred), time_hint or datetime_time(hour=hour))
        except ValueError:
            return None
    return None


def _extract_time_hint(text: str) -> datetime_time | None:
    """Extract explicit clock time from reminder text such as 10am or 14:30."""
    lowered = (text or "").lower()
    ampm_match = re.search(r"\b([1-9]|1[0-2])(?::([0-5]\d))?\s*(am|pm)\b", lowered)
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2) or "0")
        meridiem = ampm_match.group(3)
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return datetime_time(hour=hour, minute=minute)

    clock_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
    if clock_match:
        return datetime_time(hour=int(clock_match.group(1)), minute=int(clock_match.group(2)))
    return None


def _dedupe_extracted_action_items(action_items, *, raw_text: str, local_date: date) -> list[tuple]:
    """Drop exact duplicates and redundant combined reminders from LLM extraction."""
    prepared = []
    for item in action_items:
        description = (item.description or "").strip()
        if not description:
            continue
        due_at = _parse_action_due_at(item.due_at, local_date) or _infer_action_due_at_from_text(
            description,
            raw_text,
            local_date,
        )
        if not _is_action_item_worth_storing(description, raw_text, due_at):
            continue
        tokens = _action_tokens(description)
        prepared.append((item, due_at, tokens, _action_key(description, due_at, item.status)))

    exact_seen: set[tuple] = set()
    unique = []
    for item, due_at, tokens, key in prepared:
        if key in exact_seen:
            continue
        exact_seen.add(key)
        unique.append((item, due_at, tokens, key))

    result = []
    for index, (item, due_at, tokens, _key) in enumerate(unique):
        description_lower = (item.description or "").lower()
        looks_combined = " and " in description_lower or " both " in description_lower
        if looks_combined and _covered_by_component_actions(index, tokens, due_at, unique):
            continue
        result.append((item, due_at))
    return result


def _action_key(description: str, due_at: datetime | None, status: str | None) -> tuple:
    normalized = " ".join(_action_tokens(description))
    due_key = due_at.isoformat(timespec="minutes") if due_at else ""
    return normalized, due_key, (status or "open").lower()


def _is_action_item_worth_storing(description: str, raw_text: str, due_at: datetime | None) -> bool:
    """Keep open tasks high precision; store undated tasks only when the entry is explicit."""
    if due_at is not None:
        return True

    combined = f"{description}\n{raw_text}".lower()
    explicit_patterns = (
        "action item",
        "deadline",
        "due ",
        "follow up",
        "i have to",
        "i need to",
        "i should",
        "i must",
        "i will",
        "i'm going to",
        "im going to",
        "i plan to",
        "need to",
        "next step",
        "next sprint",
        "plan to",
        "remind me",
        "todo",
        "to-do",
    )
    return any(pattern in combined for pattern in explicit_patterns)


def _action_tokens(description: str) -> list[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "at",
        "both",
        "dana",
        "for",
        "me",
        "my",
        "of",
        "please",
        "remind",
        "reminder",
        "send",
        "task",
        "tasks",
        "the",
        "to",
        "tomorrow",
        "user",
    }
    words = re.findall(r"[a-z0-9]+", (description or "").lower())
    return [word for word in words if word not in stop_words and len(word) > 1]


def _covered_by_component_actions(index: int, tokens: list[str], due_at: datetime | None, unique: list[tuple]) -> bool:
    if len(tokens) < 4:
        return False
    token_set = set(tokens)
    matches = 0
    for other_index, (_, other_due_at, other_tokens, _) in enumerate(unique):
        if other_index == index or not other_tokens:
            continue
        if due_at and other_due_at and due_at != other_due_at:
            continue
        other_set = set(other_tokens)
        overlap = len(token_set & other_set)
        if overlap >= min(len(other_set), 3) and overlap / max(1, len(other_set)) >= 0.6:
            matches += 1
    return matches >= 2


def _dedupe_extracted_memories(memories) -> list:
    """Remove exact and near-substring duplicate memories from repetitive entries."""
    unique = []
    normalized_seen: set[str] = set()
    for memory in memories:
        text = (memory.text or "").strip()
        if not text:
            continue
        normalized = _normalize_memory_text(text)
        if normalized in normalized_seen:
            continue
        if any(_memory_texts_overlap(normalized, existing) for existing in normalized_seen):
            continue
        normalized_seen.add(normalized)
        unique.append(memory)
    return unique


def _normalize_memory_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _memory_texts_overlap(candidate: str, existing: str) -> bool:
    if len(candidate) < 24 or len(existing) < 24:
        return False
    short, long = sorted((candidate, existing), key=len)
    if short in long and len(short) / max(1, len(long)) >= 0.55:
        return True
    short_tokens = set(short.split())
    long_tokens = set(long.split())
    if not short_tokens:
        return False
    return len(short_tokens & long_tokens) / len(short_tokens) >= 0.9


def _rel_weight(rel_type: str) -> float:
    weights = {
        "knows": 3.0,
        "works_with": 2.5,
        "works_on": 2.5,
        "uses_technology": 2.0,
        "met_at": 2.0,
        "located_at": 1.5,
        "discussed": 1.0,
        "created": 2.0,
        "read": 1.5,
        "associated_with": 1.0,
    }
    return weights.get(rel_type, 1.0)


def _missing_relationship_entity_type(relation_type: str, *, source: bool) -> str:
    relation = (relation_type or "").strip().lower()
    if source:
        if relation in {"located_at"}:
            return "event"
        if relation in {"uses_technology"}:
            return "project"
        return "person"
    if relation in {"met_at", "located_at"}:
        return "place"
    if relation in {"uses", "uses_technology", "runs_on", "powered_by"}:
        return "technology"
    if relation in {"works_on", "contributed_to", "studying_for", "preparing_for", "tracking"}:
        return "project"
    if relation in {"read"}:
        return "document"
    if relation in {"created", "built", "wrote", "imported", "saved"}:
        return "idea"
    if relation in {"discussed", "mentioned", "said"}:
        return "topic"
    return "concept"


# Keywords that indicate genuinely sensitive content
CONFIDENTIAL_PATTERNS = [
    "investment",
    "acquisition",
    "merge",
    "valuation",
    "revenue",
    "profit margin",
    "non-public",
    "trade secret",
    "confidential",
    "NDA",
    "board meeting",
    "quarterly results",
    "earnings",
    "pre-IPO",
    "fundraising",
    "cap table",
    "term sheet",
    "due diligence",
    "proprietary",
]

PERSONAL_PATTERNS = [
    "office",
    "desk",
    "commute",
    "lunch",
    "coworker",
    "colleague",
    "worked",
    "meeting",
    "email",
    "cubicle",
    "manager",
    "boss",
    "clocked",
    "shift",
    "breakroom",
    "workstation",
]


def _normalize_sensitivity(extraction) -> None:
    """Fix LLM over-tagging: downgrade confidential_work unless genuinely sensitive."""
    entry_text = " ".join([m.text for m in extraction.memories] + [e.summary or "" for e in extraction.events]).lower()

    has_personal_only = all(p not in entry_text for p in CONFIDENTIAL_PATTERNS)

    # If no genuinely confidential patterns exist, downgrade
    if has_personal_only:
        # Remove confidential_work from the top-level tags
        if "confidential_work" in extraction.sensitivity_tags:
            extraction.sensitivity_tags.remove("confidential_work")

        # Downgrade individual memories and events
        for mem in extraction.memories:
            if mem.sensitivity == "confidential_work":
                mem.sensitivity = "personal"
        for evt in extraction.events:
            if evt.sensitivity == "confidential_work":
                evt.sensitivity = "personal"


def _auto_link_entities_to_memories(session, raw_entry_id: str):
    """Post-processing: scan memory text for entity names and auto-create subject/object links.

    This catches cases where the LLM extracted a concept (e.g., 'Brightwater apartment')
    and mentioned it in memory text but didn't set subject_entity_id.
    """
    from thoughtpins.db import Entity, Memory

    memories = session.query(Memory).filter(Memory.raw_entry_id == raw_entry_id).all()
    owner_user_id = memories[0].user_id if memories else None
    entities_q = session.query(Entity)
    if owner_user_id:
        entities_q = entities_q.filter(Entity.user_id == owner_user_id)
    all_entities = entities_q.all()

    if not memories or not all_entities:
        return

    links_created = 0
    for mem in memories:
        if mem.subject_entity_id and mem.object_entity_id:
            continue  # Already fully linked

        mem_text_lower = mem.text.lower()
        for entity in all_entities:
            name_lower = entity.canonical_name.lower()
            # Skip if name is too short (would produce false matches)
            if len(name_lower) < 4:
                continue
            # Check if entity name appears in memory text
            if name_lower in mem_text_lower:
                if not mem.subject_entity_id and entity.type in ("person", "topic", "project"):
                    mem.subject_entity_id = entity.id
                    links_created += 1
                elif not mem.object_entity_id and entity.id != mem.subject_entity_id:
                    mem.object_entity_id = entity.id
                    links_created += 1

    if links_created > 0:
        logger.debug("Auto-linked {} entity references for entry {}", links_created, raw_entry_id)


def _pick_max_sensitivity(tags: list[str]) -> str:
    order = [
        "public_ok",
        "personal",
        "location_sensitive",
        "finance",
        "health",
        "relationship",
        "substance_use",
        "sensitive_third_party",
        "confidential_work",
        "private",
    ]
    if not tags:
        return "personal"
    max_idx = max((order.index(t) if t in order else -1) for t in tags)
    return order[max_idx] if max_idx >= 0 else "personal"
