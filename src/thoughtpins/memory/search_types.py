"""Value types and lexical constants for hybrid memory search."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    memory_id: str
    text: str
    memory_type: str
    local_date: str
    confidence: str
    sensitivity: str
    source_entry_id: str
    score: float = 0.0
    entity_names: list[str] = field(default_factory=list)
    source_kind: str = "journal"
    source_title: str = ""
    evidence_text: str = ""
    predicate: str = ""
    source_provenance: str = ""
    evidence_metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_sources: list[str] = field(default_factory=list)
    source_ranks: dict[str, int] = field(default_factory=dict)
    ranking_signals: dict[str, float] = field(default_factory=dict)
    ranking_policy: str = "social-episodic-v2"
    user_importance: int | None = None
    entry_salience: float | None = None
    entry_salience_uncertainty: float | None = None


@dataclass(frozen=True)
class QueryAnalysis:
    raw: str
    normalized: str
    token_sequence: tuple[str, ...]
    tokens: set[str]
    high_value_tokens: set[str]
    phrases: tuple[str, ...]
    specificity: float


_STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "been",
    "being",
    "but",
    "can",
    "did",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "her",
    "him",
    "his",
    "how",
    "into",
    "its",
    "not",
    "our",
    "out",
    "remember",
    "show",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "would",
    "you",
    "your",
}
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}")
