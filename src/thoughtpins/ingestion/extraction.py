"""LLM extraction for structured journal memory."""

from __future__ import annotations

from collections.abc import Sequence

from loguru import logger
from pydantic import ValidationError

from thoughtpins.ingestion.entity_type_correction import correct_entity_types as _correct_entity_types
from thoughtpins.ingestion.explicit_facts import recover_explicit_facts
from thoughtpins.ingestion.extraction_recovery import ensure_durable_memory
from thoughtpins.llm import (
    AttributedQuote,
    ExtractedActionItem,
    ExtractedEntity,
    ExtractedEvent,
    ExtractedExpense,
    ExtractedMemory,
    ExtractedRelationship,
    ExtractionResult,
    SceneAnalysis,
    SocialDynamic,
    TimelineItem,
)
from thoughtpins.llm.client import get_llm_client
from thoughtpins.llm.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_user_prompt,
    get_extraction_schema_json,
)


def extract_from_entry(raw_text: str, local_datetime: str) -> ExtractionResult:
    """Run the LLM extraction pipeline on a raw journal entry."""
    llm = get_llm_client()
    schema_json = get_extraction_schema_json()

    system = EXTRACTION_SYSTEM_PROMPT
    user = build_extraction_user_prompt(local_datetime, raw_text, schema_json)

    logger.info("Running LLM extraction for {} chars of text", len(raw_text))

    raw_result = llm.extract_json(system, user, schema_json)

    # Validate with Pydantic
    try:
        result = ExtractionResult.model_validate(raw_result)
        logger.info(
            "Extraction complete: {} entities, {} events, {} memories, {} relationships",
            len(result.entities),
            len(result.events),
            len(result.memories),
            len(result.relationships),
        )
        return _finalize_extraction(
            result,
            raw_text=raw_text,
            llm=llm,
            system_prompt=system,
            user_prompt=user,
            schema_json=schema_json,
        )
    except ValidationError as e:
        logger.warning("Full validation failed ({} errors), attempting partial recovery", e.error_count())

        # Recover what we can -- validate each sub-list individually
        recovered = ExtractionResult(
            scene_analysis=_validate_model(raw_result.get("scene_analysis"), SceneAnalysis) or SceneAnalysis(),
            entry_summary=raw_result.get("entry_summary", "Partial extraction"),
            entry_type=raw_result.get("entry_type", "journal_entry"),
            sensitivity_tags=_safe_list(raw_result.get("sensitivity_tags"), str),
        )

        recovered.entities = _validate_items(raw_result.get("entities", []), ExtractedEntity, "entity")
        recovered.events = _validate_items(raw_result.get("events", []), ExtractedEvent, "event")
        recovered.memories = _validate_items(raw_result.get("memories", []), ExtractedMemory, "memory")
        recovered.relationships = _validate_items(
            raw_result.get("relationships", []), ExtractedRelationship, "relationship"
        )
        recovered.social_dynamics = _validate_items(
            raw_result.get("social_dynamics", []), SocialDynamic, "social_dynamic"
        )
        recovered.timeline_items = _validate_items(raw_result.get("timeline_items", []), TimelineItem, "timeline_item")
        recovered.action_items = _validate_items(raw_result.get("action_items", []), ExtractedActionItem, "action_item")
        recovered.expenses = _validate_items(raw_result.get("expenses", []), ExtractedExpense, "expense")
        recovered.quotes = _safe_list(raw_result.get("quotes"), str)
        recovered.attributed_quotes = _validate_items(
            raw_result.get("attributed_quotes", []), AttributedQuote, "attributed_quote"
        )
        recovered.open_questions = _safe_list(raw_result.get("open_questions"), str)

        logger.info(
            "Partial recovery: {} entities, {} events, {} memories, {} relationships",
            len(recovered.entities),
            len(recovered.events),
            len(recovered.memories),
            len(recovered.relationships),
        )

        # Paragraph-split retry: if recovery got very little and text is long, split and retry
        if len(recovered.memories) < 2 and len(raw_text) > 300:
            logger.info("Attempting paragraph-split extraction for {} chars", len(raw_text))
            paragraphs = [p.strip() for p in raw_text.split(".") if len(p.strip()) > 20]
            if len(paragraphs) >= 2:
                merged = _paragraph_extract(llm, system, paragraphs, local_datetime, schema_json)
                if merged and len(merged.memories) > len(recovered.memories):
                    logger.info(
                        "Paragraph-split improved: {} memories (was {})", len(merged.memories), len(recovered.memories)
                    )
                    return recover_explicit_facts(merged, raw_text)

        return _finalize_extraction(
            recovered,
            raw_text=raw_text,
            llm=llm,
            system_prompt=system,
            user_prompt=user,
            schema_json=schema_json,
        )


def _finalize_extraction(
    result: ExtractionResult,
    *,
    raw_text: str,
    llm,
    system_prompt: str,
    user_prompt: str,
    schema_json: str,
) -> ExtractionResult:
    durable = ensure_durable_memory(
        result,
        raw_text=raw_text,
        llm=llm,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_json=schema_json,
    )
    return recover_explicit_facts(durable, raw_text)


def _paragraph_extract(llm, system: str, paragraphs: list[str], timestamp: str, schema_json: str):
    """Extract from each paragraph separately and merge results."""
    all_entities = []
    all_events = []
    all_memories = []
    all_relationships = []
    all_social_dynamics = []
    all_timeline_items = []
    all_action_items = []
    all_expenses = []
    all_quotes = []
    all_attributed_quotes = []
    all_open_questions = []
    sensitivity_tags = []
    scene_analyses = []
    summaries = []

    for para in paragraphs[:5]:  # Max 5 paragraphs to limit API calls
        try:
            user = build_extraction_user_prompt(timestamp, para, schema_json)
            raw = llm.extract_json(system, user, schema_json)
            result = ExtractionResult.model_validate(raw)
            all_entities.extend(result.entities)
            all_events.extend(result.events)
            all_memories.extend(result.memories)
            all_relationships.extend(result.relationships)
            all_social_dynamics.extend(result.social_dynamics)
            all_timeline_items.extend(result.timeline_items)
            all_action_items.extend(result.action_items)
            all_expenses.extend(result.expenses)
            all_quotes.extend(result.quotes)
            all_attributed_quotes.extend(result.attributed_quotes)
            all_open_questions.extend(result.open_questions)
            sensitivity_tags.extend(result.sensitivity_tags)
            scene_analyses.append(result.scene_analysis)
            if result.entry_summary:
                summaries.append(result.entry_summary)
        except Exception:
            continue

    if not all_memories:
        return None

    # Deduplicate by text similarity
    seen_texts = set()
    deduped_memories = []
    for m in all_memories:
        key = m.text[:60].lower()
        if key not in seen_texts:
            seen_texts.add(key)
            deduped_memories.append(m)

    deduped_entities = _dedupe_entities(all_entities)
    deduped_events = _dedupe_events(all_events)

    return ExtractionResult(
        entry_summary=". ".join(summaries) if summaries else "Paragraph-split extraction",
        entry_type="journal_entry",
        entities=deduped_entities,
        events=deduped_events,
        memories=deduped_memories,
        relationships=list({(r.source, r.relation_type, r.target): r for r in all_relationships}.values()),
        social_dynamics=_dedupe_models(
            all_social_dynamics,
            lambda item: (item.observation or item.description).strip().casefold(),
        ),
        timeline_items=_dedupe_models(
            all_timeline_items,
            lambda item: (item.description, item.temporal_expression),
        ),
        action_items=_dedupe_models(
            all_action_items,
            lambda item: (item.description.strip().casefold(), item.due_at),
        ),
        expenses=_dedupe_models(
            all_expenses,
            lambda item: (item.amount, item.currency, item.merchant_or_place, item.reason),
        ),
        quotes=_dedupe_values(all_quotes),
        attributed_quotes=_dedupe_models(
            all_attributed_quotes,
            lambda item: (item.speaker.strip().casefold(), item.quote.strip().casefold()),
        ),
        open_questions=_dedupe_values(all_open_questions),
        sensitivity_tags=_dedupe_values(sensitivity_tags),
        scene_analysis=_merge_scene_analyses(scene_analyses),
    )


def _dedupe_entities(entities):
    seen = set()
    result = []
    for e in entities:
        key = e.surface_name.lower()
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result


def _dedupe_events(events):
    seen = set()
    result = []
    for e in events:
        key = e.name.lower()[:40]
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result


def _validate_items(items: Sequence[object], model_cls, label: str) -> list:
    """Validate individual items, skipping invalid ones."""
    valid = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        try:
            valid.append(model_cls.model_validate(item))
        except ValidationError as ve:
            logger.debug("Skipping invalid {} at index {}: {}", label, i, ve)
    return valid


def _validate_model(item: object, model_cls):
    if not isinstance(item, dict):
        return None
    try:
        return model_cls.model_validate(item)
    except ValidationError:
        return None


def _dedupe_models(items: Sequence[object], key_fn) -> list:
    seen = set()
    result = []
    for item in items:
        key = key_fn(item)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_values(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item.strip())
    return result


def _merge_scene_analyses(items: Sequence[SceneAnalysis]) -> SceneAnalysis:
    if not items:
        return SceneAnalysis()
    first = items[0]
    summaries = _dedupe_values([item.social_dynamics_summary for item in items if item.social_dynamics_summary])
    return SceneAnalysis(
        domain=next((item.domain for item in items if item.domain != "mixed"), first.domain),
        primary_topics=_dedupe_values([topic for item in items for topic in item.primary_topics]),
        emotional_tone=next(
            (item.emotional_tone for item in items if item.emotional_tone != "neutral"),
            first.emotional_tone,
        ),
        social_dynamics_summary=" ".join(summaries),
        entry_type=next(
            (item.entry_type for item in items if item.entry_type != "narrative"),
            first.entry_type,
        ),
        narrative_threads=_dedupe_values([thread for item in items for thread in item.narrative_threads]),
        unresolved_threads=_dedupe_values([thread for item in items for thread in item.unresolved_threads]),
    )


def _safe_list(val, _typ=str) -> list:
    if isinstance(val, list):
        return [x for x in val if isinstance(x, _typ)]
    return []


def correct_entity_types(extraction: ExtractionResult, raw_text: str) -> ExtractionResult:
    """Compatibility seam for callers and tests that patch this module's client factory."""
    return _correct_entity_types(extraction, raw_text, llm_factory=get_llm_client)
