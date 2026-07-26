"""Entity resolution -- context-aware matching using LLM semantic reasoning."""

from __future__ import annotations

import json
import re
import threading
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.db import Entity
from thoughtpins.utils import ENTITY_TYPES

# Thread-safe cache: (surface_name_lower, candidate_name_lower, context_hash) -> canonical | None
_resolution_cache: dict[tuple[str, str, int], Optional[str]] = {}
_cache_lock = threading.Lock()

_ENTITY_TYPE_ALIASES = {
    "human": "person",
    "people": "person",
    "person_name": "person",
    "name": "person",
    "location": "place",
    "venue": "place",
    "merchant": "place",
    "source": "document",
    "article": "document",
    "book": "document",
    "paper": "document",
    "essay": "document",
    "tech": "technology",
    "tool": "technology",
    "framework": "technology",
    "database": "technology",
    "model": "technology",
    "company": "organization",
    "org": "organization",
    "business": "organization",
    "startup": "organization",
    "idea": "idea",
    "thought": "concept",
    "quote": "concept",
    "phrase": "concept",
    "theme": "topic",
    "task": "project",
    "goal": "project",
    "initiative": "project",
}

_SELF_NAMES = {"i", "me", "myself", "user", "the user"}

_GENERIC_NON_PERSON_NAMES = {
    "conversation",
    "cortado",
    "day",
    "memory",
    "move",
    "pilsner",
    "groceries",
    "outcome",
    "outcomes",
    "performance",
    "social read",
    "today",
    "the day",
    "the room",
    "the conversation",
    "the outcome",
    "the plan",
    "the version",
}

_ABSTRACT_CONCEPT_NAMES = {
    "agency",
    "ambition",
    "attention",
    "caution",
    "discipline",
    "fear",
    "habit",
    "hype",
    "humility",
    "identity",
    "privacy",
    "prayer",
    "resolve",
    "quitting",
    "reliability",
    "service",
    "spirituality",
    "surrender",
    "truth",
}

_PERSON_CONTEXT_MARKERS = {
    "said",
    "told",
    "asked",
    "replied",
    "texted",
    "called",
    "met",
    "with",
    "friend",
    "coworker",
    "colleague",
    "sister",
    "brother",
    "mom",
    "dad",
    "wife",
    "husband",
    "manager",
    "founder",
    "ceo",
    "cto",
}

_EVENT_NAME_MARKERS = {
    "chat",
    "call",
    "conversation",
    "meeting",
    "session",
    "workshop",
    "dinner",
    "lunch",
    "coffee",
    "review",
    "exam",
    "test",
}

_PROJECT_NAME_MARKERS = {
    "app",
    "api",
    "codebase",
    "platform",
    "product",
    "prototype",
    "workflow",
    "system",
    "service",
    "model",
    "demo",
    "backend",
    "frontend",
    "maintenance",
    "notes",
}

_PLACE_NAME_MARKERS = {
    "bar",
    "cafe",
    "coffee",
    "market",
    "store",
    "workspace",
    "office",
    "restaurant",
    "apartment",
}

_RESOLUTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "before",
    "for",
    "from",
    "in",
    "into",
    "it",
    "my",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "user",
    "with",
    "your",
}


def _meaningful_name_words(name: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", name.lower()) if word and word not in _RESOLUTION_STOPWORDS}


def _looks_like_acronym_match(surface_name: str, canonical_name: str) -> bool:
    surface_token = re.sub(r"[^A-Za-z0-9]", "", surface_name)
    if not surface_token or len(surface_token) > 8 or not surface_token.isupper():
        return False
    words = re.findall(r"[A-Za-z0-9]+", canonical_name)
    if len(words) < 2:
        return False
    acronym = "".join(word[0].upper() for word in words if word)
    return surface_token == acronym


def _near_person_marker(surface_name: str, raw_text: str) -> bool:
    if not raw_text:
        return False
    raw_lower = raw_text.lower()
    name_lower = surface_name.lower()
    idx = raw_lower.find(name_lower)
    if idx < 0:
        return False
    context = raw_lower[max(0, idx - 80) : idx + len(name_lower) + 80]
    return any(marker in context for marker in _PERSON_CONTEXT_MARKERS)


def _normalize_entity_type(
    surface_name: str,
    canonical_guess: str,
    entity_type: str,
    raw_text: str = "",
) -> str:
    """Normalize LLM-provided entity types before anything can be persisted."""
    type_value = (entity_type or "").strip().lower()
    type_value = _ENTITY_TYPE_ALIASES.get(type_value, type_value)
    if type_value not in ENTITY_TYPES:
        type_value = "person" if surface_name.strip().lower() in _SELF_NAMES else "concept"

    name = (canonical_guess or surface_name or "").strip()
    name_lower = name.lower()
    word_count = len(name_lower.split())

    if name_lower in _SELF_NAMES:
        return "person"

    if type_value == "person":
        if name_lower in _GENERIC_NON_PERSON_NAMES:
            return "concept"
        if name_lower in _ABSTRACT_CONCEPT_NAMES:
            return "concept"
        if word_count >= 4:
            return "concept"
        if any(marker in name_lower for marker in _EVENT_NAME_MARKERS):
            return "event"
        if any(marker in name_lower for marker in _PROJECT_NAME_MARKERS):
            return "project"
        if any(marker in name_lower for marker in _PLACE_NAME_MARKERS):
            return "place"
        if word_count >= 3 and not _near_person_marker(name, raw_text):
            return "concept"

    return type_value


def _context_window(raw_text: str, surface_name: str, window: int = 120) -> str:
    """Extract the text surrounding a surface name mention for context."""
    idx = raw_text.lower().find(surface_name.lower())
    if idx == -1:
        return raw_text[: window * 2]
    start = max(0, idx - window)
    end = min(len(raw_text), idx + len(surface_name) + window)
    return raw_text[start:end]


def _context_hash(raw_text: str) -> int:
    """Fast hash of context for cache key."""
    return hash(raw_text[:500].lower()) & 0x7FFFFFFF


def _batch_semantic_resolve(
    new_entities: list[dict],
    existing_entities: list[Entity],
    raw_text: str,
) -> dict[str, Optional[str]]:
    """
    Send ALL new entities + ALL existing entities to the LLM in one batched call.
    LLM sees the full entry context and uses general knowledge to determine
    which new names refer to the same thing as existing entities.

    Returns: {surface_name: canonical_name or None}
    """
    if not new_entities or not existing_entities:
        return {}

    ctx_hash = _context_hash(raw_text)

    # Build existing entity list
    existing_lines = []
    for e in existing_entities:
        aliases = e.aliases_json or []
        alias_str = f" (aka: {', '.join(aliases[:5])})" if aliases else ""
        existing_lines.append(f"  [{e.type}] {e.canonical_name}{alias_str}")

    # Build new entity list with context windows
    new_lines = []
    for ne in new_entities:
        name = ne["surface_name"]
        ntype = ne["type"]
        ctx = _context_window(raw_text, name)
        new_lines.append(f'  - "{name}" (currently typed as: {ntype})')
        new_lines.append(f"    context: ...{ctx}...")

    prompt = f"""You are resolving entity names in a personal journal entry. The user wrote the following:

FULL ENTRY:
{raw_text[:2000]}

EXISTING ENTITIES IN DATABASE:
{chr(10).join(existing_lines) if existing_lines else "(none yet)"}

NEW NAMES TO RESOLVE (with surrounding context):
{chr(10).join(new_lines)}

For EACH new name, determine if it refers to the SAME real-world thing as any existing entity.
Use the FULL ENTRY CONTEXT and your general knowledge to decide.

Rules:
- Two names refer to the SAME thing ONLY if they unambiguously mean the same entity in this context.
- "SPY" in a finance/investing entry refers to the S&P 500 ETF.
- "SPY" in an espionage/security entry does NOT refer to the S&P 500 ETF.
- "benching" in a gym/fitness context refers to "bench press" (the exercise).
- "benching" in a workplace context might mean removing someone from a project.
- "CFA" in a studying/exam context is the certification. In a different context it could be someone's initials.
- Use the surrounding context words to disambiguate.
- If a name refers to something genuinely NEW (not in existing list), say "NEW".
- If you're unsure, say "NEW" -- better to keep separate than merge incorrectly.

Return JSON:
{{"results": [
  {{"name": "SPY", "resolves_to": "S&P 500 ETF"}},
  {{"name": "benching", "resolves_to": "Bench Press"}},
  {{"name": "something new", "resolves_to": "NEW"}}
]}}

Only JSON. No commentary."""

    try:
        from thoughtpins.llm.client import get_llm_client

        llm = get_llm_client()
        response = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )

        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1:
            return {}

        data = json.loads(response[start : end + 1])
        results = data.get("results", [])

        resolved = {}
        for r in results:
            name = r.get("name", "")
            target = r.get("resolves_to", "NEW")
            if target and target.upper() != "NEW":
                resolved[name] = target
                # Cache the result
                for e in existing_entities:
                    if e.canonical_name.lower() == target.lower():
                        with _cache_lock:
                            _resolution_cache[(name.lower(), e.canonical_name.lower(), ctx_hash)] = e.canonical_name
            else:
                resolved[name] = None  # explicitly NEW

        if resolved:
            logger.info("Context-aware resolution: {} entities resolved", len([v for v in resolved.values() if v]))

        return resolved

    except Exception as e:
        logger.debug("Batch semantic resolve skipped: {}", e)
        return {}


def resolve_entity(
    session: Session,
    surface_name: str,
    canonical_guess: str,
    entity_type: str,
    raw_text: str = "",
    user_id: str | None = None,
) -> tuple[Optional[Entity], bool]:
    """Match a surface name to an existing entity using context-aware resolution."""
    ctx_hash = _context_hash(raw_text) if raw_text else 0

    # 1. Exact canonical match
    existing_q = session.query(Entity).filter(
        Entity.type == entity_type,
        Entity.canonical_name == canonical_guess,
    )
    if user_id:
        existing_q = existing_q.filter(Entity.user_id == user_id)
    existing = existing_q.first()
    if existing:
        return existing, False

    # 2. Alias match
    all_entities_q = session.query(Entity).filter(Entity.type == entity_type)
    if user_id:
        all_entities_q = all_entities_q.filter(Entity.user_id == user_id)
    all_entities = all_entities_q.all()
    for ent in all_entities:
        aliases = ent.aliases_json or []
        if surface_name in aliases or canonical_guess in aliases:
            return ent, False

    # 3. Case-insensitive canonical match
    for ent in all_entities:
        if ent.canonical_name.lower() == canonical_guess.lower():
            return ent, False

    # 4. Context-aware semantic resolution (for non-person types)
    if entity_type != "person" and raw_text and all_entities:
        # Check cache first (thread-safe read)
        for ent in all_entities:
            cache_key = (surface_name.lower(), ent.canonical_name.lower(), ctx_hash)
            with _cache_lock:
                cached = _resolution_cache.get(cache_key)
            if cached == ent.canonical_name:
                _add_alias(ent, surface_name)
                return ent, False

        # Filter to candidates that share meaningful words or look like acronyms.
        # This avoids an LLM call just because two names share stopwords like "the".
        surf_words = _meaningful_name_words(surface_name)
        candidates = [
            e
            for e in all_entities
            if surf_words & _meaningful_name_words(e.canonical_name)
            or _looks_like_acronym_match(surface_name, e.canonical_name)
        ]

        if candidates:
            resolved = _batch_semantic_resolve(
                [{"surface_name": surface_name, "type": entity_type}],
                candidates[:15],  # Limit to avoid huge prompts
                raw_text,
            )

            match_name = resolved.get(surface_name)
            if match_name:
                for ent in all_entities:
                    if ent.canonical_name.lower() == match_name.lower():
                        _add_alias(ent, surface_name)
                        return ent, False

    # 5. Conservative first-name match for people only
    if entity_type == "person":
        surface_first = surface_name.split()[0] if surface_name.split() else surface_name
        matches = [e for e in all_entities if e.canonical_name.lower().startswith(surface_first.lower())]
        if len(matches) == 1:
            return matches[0], False

    return None, True


def _add_alias(entity: Entity, surface_name: str):
    """Add surface name as alias if not already present."""
    aliases = entity.aliases_json or []
    if surface_name not in aliases and surface_name != entity.canonical_name:
        aliases.append(surface_name)
        entity.aliases_json = aliases


def create_or_get_entity(
    session: Session,
    surface_name: str,
    canonical_guess: str,
    entity_type: str,
    sensitivity: str = "personal",
    confidence: str = "observed_by_user",
    raw_text: str = "",
    user_id: str | None = None,
) -> Entity:
    """Resolve or create an entity using context-aware matching."""
    entity_type = _normalize_entity_type(surface_name, canonical_guess, entity_type, raw_text)
    existing, is_new = resolve_entity(
        session,
        surface_name,
        canonical_guess,
        entity_type,
        raw_text=raw_text,
        user_id=user_id,
    )

    if existing is not None and not is_new:
        _add_alias(existing, surface_name)
        return existing

    # Create new entity
    display_name = canonical_guess
    if len(surface_name.split()) == 1 and entity_type == "person":
        first = surface_name.split()[0]
        count = (
            session.query(Entity)
            .filter(Entity.type == entity_type, Entity.canonical_name.like(f"{first}%"))
            .filter(Entity.user_id == user_id if user_id else True)
            .count()
        )
        if count > 0:
            display_name = f"{canonical_guess} (unknown {count + 1})"

    entity = Entity(
        user_id=user_id,
        type=entity_type,
        canonical_name=display_name,
        aliases_json=[surface_name] if surface_name != display_name else [],
        sensitivity=sensitivity,
        confidence=confidence,
    )
    session.add(entity)
    session.flush()
    logger.info("Created new entity: {} [{}]", display_name, entity.id)
    return entity
