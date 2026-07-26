"""Canonical, bounded text projection for deterministic reranking."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from thoughtpins.memory.search_types import SearchResult

_INDEXED_METADATA_FIELDS = (
    "attributed_to",
    "speaker",
    "reported_by",
    "people_involved",
    "participants",
    "place",
    "location",
    "venue",
    "motivation",
    "reason",
    "cause",
    "consequence",
    "outcome",
    "topics",
    "key_concepts",
)


def build_ranking_evidence(result: SearchResult) -> str:
    """Project only retrieval-relevant fields into the lexical ranker.

    Arbitrary structured metadata is intentionally excluded. The allowlist
    keeps ranking explainable and prevents unrelated provider payloads from
    changing retrieval order when document schemas evolve.
    """
    values: list[str] = [
        result.text,
        result.evidence_text,
        result.source_title,
        result.predicate,
        *result.entity_names,
    ]
    for key in _INDEXED_METADATA_FIELDS:
        values.extend(_scalar_texts(result.evidence_metadata.get(key)))
    return " ".join(_deduplicate(value for value in values if value.strip()))


def _scalar_texts(value: Any) -> list[str]:
    if value is None or isinstance(value, Mapping):
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return [text for item in value if (text := _scalar_text(item))]
    text = _scalar_text(value)
    return [text] if text else []


def _scalar_text(value: Any) -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return ""
    return str(value).strip()


def _deduplicate(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
