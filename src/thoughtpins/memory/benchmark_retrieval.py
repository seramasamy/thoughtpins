"""Small, dependency-free retrieval primitives for external benchmarks."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from statistics import fmean

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "did",
        "do",
        "for",
        "from",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "the",
        "to",
        "was",
        "what",
        "when",
        "where",
        "who",
        "why",
        "with",
    }
)


@dataclass(frozen=True)
class CaseRank:
    relevant_ids: frozenset[str]
    ranked_ids: tuple[str, ...]


@dataclass(frozen=True)
class AggregateRankMetrics:
    case_count: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mean_reciprocal_rank: float
    mean_ndcg_at_10: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def rank_documents_bm25(query: str, documents: list[str]) -> list[tuple[int, float]]:
    """Return document indexes and normalized BM25 scores in rank order."""
    if not documents:
        return []
    query_terms = set(_tokens(query))
    document_tokens = [_tokens(document) for document in documents]
    if not query_terms:
        return [(index, 0.0) for index in range(len(documents))]

    document_frequency = {term: sum(1 for tokens in document_tokens if term in set(tokens)) for term in query_terms}
    document_count = len(documents)
    idf = {
        term: math.log(1.0 + ((document_count - frequency + 0.5) / (frequency + 0.5)))
        for term, frequency in document_frequency.items()
    }
    average_length = sum(len(tokens) for tokens in document_tokens) / max(1, document_count)
    raw_scores = [_bm25(tokens, query_terms, idf, average_length) for tokens in document_tokens]
    maximum = max(raw_scores, default=0.0)
    normalized = [score / maximum if maximum > 0 else 0.0 for score in raw_scores]
    return sorted(enumerate(normalized), key=lambda item: (-item[1], item[0]))


def aggregate_case_ranks(cases: list[CaseRank]) -> AggregateRankMetrics:
    if not cases:
        return AggregateRankMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ranks = [_first_relevant_rank(case) for case in cases]
    return AggregateRankMetrics(
        case_count=len(cases),
        recall_at_1=_mean(1.0 if rank <= 1 else 0.0 for rank in ranks),
        recall_at_5=_mean(1.0 if rank <= 5 else 0.0 for rank in ranks),
        recall_at_10=_mean(1.0 if rank <= 10 else 0.0 for rank in ranks),
        mean_reciprocal_rank=_mean(1.0 / rank if math.isfinite(rank) else 0.0 for rank in ranks),
        mean_ndcg_at_10=_mean(_ndcg_at_10(case) for case in cases),
    )


def _bm25(tokens: list[str], query_terms: set[str], idf: dict[str, float], average_length: float) -> float:
    if not tokens:
        return 0.0
    frequencies = Counter(tokens)
    k1 = 1.2
    b = 0.75
    length_ratio = len(tokens) / max(1.0, average_length)
    score = 0.0
    for term in query_terms:
        frequency = frequencies.get(term, 0)
        if not frequency:
            continue
        denominator = frequency + k1 * (1.0 - b + b * length_ratio)
        score += idf[term] * ((frequency * (k1 + 1.0)) / denominator)
    return score


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOP_WORDS]


def _first_relevant_rank(case: CaseRank) -> float:
    return next(
        (float(rank) for rank, item_id in enumerate(case.ranked_ids, start=1) if item_id in case.relevant_ids),
        math.inf,
    )


def _ndcg_at_10(case: CaseRank) -> float:
    gains = [1.0 if item_id in case.relevant_ids else 0.0 for item_id in case.ranked_ids[:10]]
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_count = min(10, len(case.relevant_ids))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal if ideal else 0.0


def _mean(values) -> float:
    materialized = list(values)
    return round(fmean(materialized), 6) if materialized else 0.0
