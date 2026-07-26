"""Semantic recovery for structurally valid but empty LLM extractions."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from pydantic import BaseModel

from thoughtpins.llm import ExtractedMemory, ExtractionResult, SceneAnalysis

_FALLBACK_MEMORY_LIMIT = 1200
_SUMMARY_LIMIT = 360
_MODEL_LIST_FIELDS = (
    "entities",
    "events",
    "memories",
    "relationships",
    "social_dynamics",
    "timeline_items",
    "action_items",
    "expenses",
    "attributed_quotes",
)
_STRING_LIST_FIELDS = ("sensitivity_tags", "quotes", "open_questions")


def ensure_durable_memory(
    result: ExtractionResult,
    *,
    raw_text: str,
    llm: Any,
    system_prompt: str,
    user_prompt: str,
    schema_json: str,
) -> ExtractionResult:
    """Guarantee that a substantive journal extraction retains recallable evidence.

    JSON schema validation cannot distinguish a genuinely empty note from a
    provider response that defaulted every collection. One semantic retry is
    allowed; after that, an attributed excerpt preserves the user's own words
    without inventing entities, claims, or relationships.
    """
    if result.memories or not raw_text.strip():
        return result

    logger.warning("Structured extraction omitted durable memories; retrying once")
    retry_prompt = (
        f"{user_prompt}\n\n"
        "RECOVERY REQUIREMENT: The prior extraction contained no durable memory. "
        "Return at least one atomic memory grounded only in RAW ENTRY. Preserve "
        "explicit names, places, amounts, quotes, reminders, and times. Do not invent details."
    )
    try:
        payload = llm.extract_json(system_prompt, retry_prompt, schema_json)
        retry = ExtractionResult.model_validate(payload)
    except Exception as exc:  # Provider SDKs do not share a stable exception base.
        logger.warning("Semantic extraction retry failed: {}", type(exc).__name__)
    else:
        if retry.memories:
            logger.info("Semantic extraction retry recovered {} memories", len(retry.memories))
            return _merge_results(result, retry)

    logger.warning("Using source-preserving fallback memory after empty extraction")
    return _with_source_fallback(result, raw_text)


def _merge_results(primary: ExtractionResult, retry: ExtractionResult) -> ExtractionResult:
    merged = primary.model_copy(deep=True)
    for field_name in _MODEL_LIST_FIELDS:
        values = [*getattr(primary, field_name), *getattr(retry, field_name)]
        setattr(merged, field_name, _dedupe_models(values))
    for field_name in _STRING_LIST_FIELDS:
        values = [*getattr(primary, field_name), *getattr(retry, field_name)]
        setattr(merged, field_name, _dedupe_strings(values))

    if retry.entry_summary and _summary_is_missing(primary.entry_summary):
        merged.entry_summary = retry.entry_summary
    if primary.scene_analysis == SceneAnalysis() and retry.scene_analysis != SceneAnalysis():
        merged.scene_analysis = retry.scene_analysis
    return merged


def _with_source_fallback(result: ExtractionResult, raw_text: str) -> ExtractionResult:
    recovered = result.model_copy(deep=True)
    excerpt = _bounded_excerpt(raw_text, _FALLBACK_MEMORY_LIMIT)
    recovered.memories.append(
        ExtractedMemory(
            memory_type="thought",
            text=f"User recorded: {excerpt}",
            subject="User",
            confidence="observed_by_user",
            epistemic_status="self_report",
            claim_status="active",
        )
    )
    if _summary_is_missing(recovered.entry_summary):
        recovered.entry_summary = _bounded_excerpt(raw_text, _SUMMARY_LIMIT)
    return recovered


def _bounded_excerpt(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    prefix = compact[: limit - 3].rsplit(" ", 1)[0].rstrip()
    return f"{prefix or compact[: limit - 3]}..."


def _summary_is_missing(summary: str) -> bool:
    return not summary.strip() or summary.strip().casefold() in {
        "extraction failed",
        "partial extraction",
    }


def _dedupe_models(items: list[BaseModel]) -> list[BaseModel]:
    seen: set[str] = set()
    unique: list[BaseModel] = []
    for item in items:
        key = json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        value = item.strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
