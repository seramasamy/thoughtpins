"""Post-extraction entity type correction with a protected owner anchor."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection
from typing import Protocol

from loguru import logger

from thoughtpins.llm import ExtractedEntity, ExtractionResult
from thoughtpins.llm.client import get_llm_client
from thoughtpins.llm.json_repair import repair_json
from thoughtpins.utils import ENTITY_TYPES


class _ChatClient(Protocol):
    def chat(self, messages: list[dict], *, temperature: float, max_tokens: int) -> str: ...


TYPE_CORRECTION_PROMPT = """You are reviewing entity types from a journal extraction. Some entities may have been mistyped by the extraction engine. Use your general knowledge and the original entry to fix any wrong types.

Original entry:
{raw_text}

Current entities with types:
{entity_list}

For each entity that has the WRONG type, return a correction. If all types are correct, return an empty list.

Rules:
- A person is ONLY an actual human being. "Portfolio", "Tokyo Trip", "Load Balancer", "Airbnb in Shibuya" are NOT people.
- If something is abstract (like "Portfolio", "User Retention", "Unit Economics") -> retype as "concept" or "topic"
- If something is a trip/event name (like "Tokyo Trip", "225lb Bench Press") -> retype as "event" or "project"
- If something describes a location -> retype as "place"
- If something is a company/brand (like "JAL", "Equinor", "ETH Zurich") -> retype as "organization"
- Use your general knowledge. CFA is a certification, not a person.
- Names that sound like human names (Derek, Priya, Michael, Lisa, Kenji, Xiaoling) are correctly "person".
- "User" is the reserved journal-owner anchor and must remain a "person".

Return JSON ONLY:
{{"corrections": [{{"surface_name": "Portfolio", "current_type": "person", "correct_type": "concept"}}]}}

If no corrections needed: {{"corrections": []}}"""

_FINANCE_HINTS = frozenset(
    "portfolio stock bond fund index ira 401k crypto dividend equity asset allocation holding position "
    "etf s&p spy qqq nasdaq dow nyse ticker share option futures forex commodity reit".split()
)
_ABSTRACT_HINTS = frozenset(
    "metric economics retention configuration issue bug feature deployment pipeline workflow strategy "
    "conversation outcome outcomes version performance".split()
)
_TRAVEL_HINTS = frozenset("trip travel vacation flight booking reservation airbnb hotel tour visit cruise".split())
_WORK_HINTS = frozenset(
    "review planning preparation prep studying exam test midterm final workshop session meeting call "
    "presentation report analysis".split()
)
_ORGANIZATION_HINTS = frozenset(
    "airlines capital partners venture startup inc corporation llc ltd bank university college hospital "
    "clinic institute school".split()
)
_PRODUCT_HINTS = frozenset("oauth api sdk app platform system service tool software hardware device".split())
_FITNESS_HINTS = frozenset("press squat deadlift curl bench cardio yoga pilates crossfit hiit".split())
_NON_PERSON_PATTERNS = (
    _FINANCE_HINTS
    | _ABSTRACT_HINTS
    | _TRAVEL_HINTS
    | _WORK_HINTS
    | _ORGANIZATION_HINTS
    | _PRODUCT_HINTS
    | _FITNESS_HINTS
)
_PERSON_INDICATORS = (
    "said",
    "told",
    "met",
    "meet",
    "introduced",
    "invited",
    "called",
    "texted",
    "emailed",
    "asked",
    "replied",
    "joined",
    "spoke",
    "talked",
    "mentioned",
    "whispered",
    "shouted",
    "my sister",
    "my brother",
    "my mom",
    "my dad",
    "my wife",
    "my husband",
    "my friend",
    "my boss",
    "my coworker",
    "my colleague",
    "my trainer",
    "professor",
    "doctor",
    "dr ",
    "ceo",
    "cto",
    "cfo",
    "vp",
    "manager",
)
_GENERIC_NON_PERSON_NAMES = {"conversation", "the day", "today", "the room"}
_JOURNAL_OWNER_ENTITY = "user"
_EVENT_NAME_HINTS = (
    "trip",
    "travel",
    "vacation",
    "flight",
    "booking",
    "airbnb",
    "hotel",
    "tour",
    "visit",
    "exam",
    "test",
    "workshop",
    "session",
    "meeting",
)
_ORGANIZATION_NAME_HINTS = (
    "airlines",
    "capital",
    "partners",
    "venture",
    "startup",
    "inc",
    "bank",
    "university",
    "hospital",
)
_PROJECT_NAME_HINTS = (
    "review",
    "planning",
    "preparation",
    "prep",
    "oauth",
    "api",
    "system",
    "service",
    "tool",
    "platform",
)
_TOPIC_NAME_HINTS = (
    "portfolio",
    "stock",
    "bond",
    "fund",
    "index",
    "ira",
    "crypto",
    "metric",
    "economics",
)


def correct_entity_types(
    extraction: ExtractionResult,
    raw_text: str,
    *,
    llm_factory: Callable[[], _ChatClient] = get_llm_client,
) -> ExtractionResult:
    """Correct clear entity-type errors while preserving the owner invariant."""
    if not extraction.entities:
        return extraction

    corrections_made = _apply_heuristic_type_corrections(extraction, raw_text, ENTITY_TYPES)
    suspicious = _suspicious_person_entities(extraction, raw_text)
    corrections_made += _review_suspicious_types(
        extraction,
        suspicious,
        raw_text,
        ENTITY_TYPES,
        llm_factory=llm_factory,
    )

    if corrections_made > 0:
        logger.info("Type correction: {} entities fixed", corrections_made)
    else:
        logger.debug("Type correction: all types already correct")
    return extraction


def _is_journal_owner_entity(entity_name: str) -> bool:
    return entity_name.casefold().strip() == _JOURNAL_OWNER_ENTITY


def _heuristic_type_fix(entity_name: str, current_type: str, raw_text: str) -> str | None:
    if (current_type or "").casefold().strip() != "person":
        return None

    name_lower = entity_name.casefold()
    if name_lower in _GENERIC_NON_PERSON_NAMES:
        return "concept"
    if _contains_name_hint(name_lower, _NON_PERSON_PATTERNS):
        return _non_person_type(name_lower)
    if _person_indicator_near_entity(name_lower, raw_text):
        return None
    # Name length is not evidence of type. Multi-part human names are common,
    # so ambiguous cases stay untouched for the constrained review pass below.
    return None


def _non_person_type(name_lower: str) -> str:
    for entity_type, hints in (
        ("event", _EVENT_NAME_HINTS),
        ("organization", _ORGANIZATION_NAME_HINTS),
        ("project", _PROJECT_NAME_HINTS),
        ("topic", _TOPIC_NAME_HINTS),
    ):
        if _contains_name_hint(name_lower, hints):
            return entity_type
    return "concept"


def _contains_name_hint(name_lower: str, hints: Collection[str]) -> bool:
    return any(hint in name_lower for hint in hints)


def _person_indicator_near_entity(name_lower: str, raw_text: str) -> bool:
    raw_lower = raw_text.casefold()
    start = 0
    while (index := raw_lower.find(name_lower, start)) >= 0:
        context_window = raw_lower[max(0, index - 80) : index + len(name_lower) + 80]
        if any(re.search(rf"\b{re.escape(indicator)}\b", context_window) for indicator in _PERSON_INDICATORS):
            return True
        start = index + len(name_lower)
    return False


def _apply_heuristic_type_corrections(
    extraction: ExtractionResult,
    raw_text: str,
    entity_types: Collection[str],
) -> int:
    corrections_made = 0
    for entity in extraction.entities:
        normalized_type = (entity.type or "").casefold().strip()
        if normalized_type and normalized_type != entity.type:
            entity.type = normalized_type
        entity_name = entity.canonical_guess or entity.surface_name
        if _is_journal_owner_entity(entity_name):
            entity.type = "person"
            continue
        corrected_type = _heuristic_type_fix(entity_name, entity.type, raw_text)
        if corrected_type and corrected_type in entity_types:
            previous_type = entity.type
            entity.type = corrected_type
            logger.info(
                "Type fixed (heuristic): '{}' {} -> {}",
                entity.surface_name,
                previous_type,
                corrected_type,
            )
            corrections_made += 1
    return corrections_made


def _suspicious_person_entities(extraction: ExtractionResult, raw_text: str) -> list[ExtractedEntity]:
    return [
        entity
        for entity in extraction.entities
        if entity.type == "person"
        and not _is_journal_owner_entity(entity.canonical_guess or entity.surface_name)
        and not _person_indicator_near_entity(
            (entity.canonical_guess or entity.surface_name).casefold(),
            raw_text,
        )
    ]


def _review_suspicious_types(
    extraction: ExtractionResult,
    suspicious: list[ExtractedEntity],
    raw_text: str,
    entity_types: Collection[str],
    *,
    llm_factory: Callable[[], _ChatClient],
) -> int:
    if not suspicious:
        return 0
    entity_list = "\n".join(f"  - {entity.surface_name} -> {entity.type}" for entity in suspicious)
    prompt = TYPE_CORRECTION_PROMPT.format(raw_text=raw_text[:1500], entity_list=entity_list)
    try:
        response = llm_factory().chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )
        corrections = _parse_type_corrections(response)
        return _apply_llm_type_corrections(extraction, corrections, entity_types)
    except Exception as exc:
        logger.debug("LLM type review skipped: {}", exc)
        return 0


def _parse_type_corrections(response: str) -> list[dict]:
    start = response.find("{")
    end = response.rfind("}")
    payload = response[start : end + 1] if start != -1 and end != -1 else response
    if not payload.strip():
        return []
    parsed = json.loads(repair_json(payload))
    corrections = parsed.get("corrections", []) if isinstance(parsed, dict) else []
    return [item for item in corrections if isinstance(item, dict)]


def _apply_llm_type_corrections(
    extraction: ExtractionResult,
    corrections: list[dict],
    entity_types: Collection[str],
) -> int:
    entity_by_name = {entity.surface_name: entity for entity in extraction.entities}
    corrections_made = 0
    for correction in corrections:
        name = correction.get("surface_name", "")
        corrected_type = correction.get("correct_type", "")
        entity = entity_by_name.get(name)
        if not name or corrected_type not in entity_types or entity is None or _is_journal_owner_entity(name):
            continue
        if entity.type == corrected_type:
            continue
        previous_type = entity.type
        entity.type = corrected_type
        logger.info("Type fixed (LLM): '{}' {} -> {}", name, previous_type, corrected_type)
        corrections_made += 1
    return corrections_made
