"""Information-retrieval metrics for deterministic memory benchmarks."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Mapping, Sequence

from thoughtpins.memory.search_types import SearchResult


@dataclass(frozen=True)
class RetrievalMetrics:
    cutoff: int
    relevant_items: int
    retrieved_unique_items: int
    relevant_retrieved: int
    precision_at_k: float
    recall_at_k: float
    average_precision_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    evidence_coverage: float
    score_margin: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class AggregateRetrievalMetrics:
    case_count: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_average_precision_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg_at_k: float
    mean_evidence_coverage: float
    mean_score_margin: float
    worst_case_ndcg_at_k: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def evaluate_ranked_results(
    results: Sequence[SearchResult],
    *,
    relevance_by_source_entry: Mapping[str, float],
    expected_terms: Sequence[str] = (),
    cutoff: int = 10,
) -> RetrievalMetrics:
    """Evaluate a ranked result list after source-event deduplication.

    Memory, raw-entry, vector, and graph candidates can all represent the same
    underlying journal event. Counting each representation as a separate hit
    would inflate quality, so metrics operate on the first result observed for
    each source entry (falling back to the memory identifier when unavailable).
    """
    if cutoff <= 0:
        raise ValueError("cutoff must be positive")
    if any(grade < 0 for grade in relevance_by_source_entry.values()):
        raise ValueError("relevance grades must be non-negative")

    unique = _deduplicate_by_source(results)[:cutoff]
    grades = [float(relevance_by_source_entry.get(_source_key(result), 0.0)) for result in unique]
    binary = [grade > 0 for grade in grades]
    relevant_total = sum(1 for grade in relevance_by_source_entry.values() if grade > 0)
    relevant_retrieved = sum(binary)

    reciprocal_rank = next((1.0 / rank for rank, hit in enumerate(binary, start=1) if hit), 0.0)
    precision_sum = 0.0
    hits = 0
    for rank, hit in enumerate(binary, start=1):
        if hit:
            hits += 1
            precision_sum += hits / rank
    average_precision = precision_sum / max(1, min(relevant_total, cutoff))

    dcg = _discounted_cumulative_gain(grades)
    ideal_grades = sorted(
        (float(grade) for grade in relevance_by_source_entry.values() if grade > 0),
        reverse=True,
    )[:cutoff]
    ideal_dcg = _discounted_cumulative_gain(ideal_grades)
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0

    evidence = "\n".join(
        " ".join(
            (
                result.text,
                result.evidence_text,
                result.source_title,
                json.dumps(result.evidence_metadata, sort_keys=True, ensure_ascii=True),
            )
        ).lower()
        for result in unique
    )
    normalized_terms = [term.strip().lower() for term in expected_terms if term.strip()]
    evidence_coverage = (
        sum(1 for term in normalized_terms if term in evidence) / len(normalized_terms) if normalized_terms else 1.0
    )

    relevant_scores = [result.score for result, hit in zip(unique, binary, strict=True) if hit]
    irrelevant_scores = [result.score for result, hit in zip(unique, binary, strict=True) if not hit]
    if relevant_scores:
        score_margin = max(relevant_scores) - (max(irrelevant_scores) if irrelevant_scores else 0.0)
    else:
        score_margin = -(max(irrelevant_scores) if irrelevant_scores else 0.0)

    return RetrievalMetrics(
        cutoff=cutoff,
        relevant_items=relevant_total,
        retrieved_unique_items=len(unique),
        relevant_retrieved=relevant_retrieved,
        precision_at_k=round(relevant_retrieved / cutoff, 6),
        recall_at_k=round(relevant_retrieved / max(1, relevant_total), 6),
        average_precision_at_k=round(average_precision, 6),
        reciprocal_rank=round(reciprocal_rank, 6),
        ndcg_at_k=round(ndcg, 6),
        evidence_coverage=round(evidence_coverage, 6),
        score_margin=round(score_margin, 6),
    )


def aggregate_retrieval_metrics(metrics: Sequence[RetrievalMetrics]) -> AggregateRetrievalMetrics:
    if not metrics:
        return AggregateRetrievalMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return AggregateRetrievalMetrics(
        case_count=len(metrics),
        mean_precision_at_k=_mean(metric.precision_at_k for metric in metrics),
        mean_recall_at_k=_mean(metric.recall_at_k for metric in metrics),
        mean_average_precision_at_k=_mean(metric.average_precision_at_k for metric in metrics),
        mean_reciprocal_rank=_mean(metric.reciprocal_rank for metric in metrics),
        mean_ndcg_at_k=_mean(metric.ndcg_at_k for metric in metrics),
        mean_evidence_coverage=_mean(metric.evidence_coverage for metric in metrics),
        mean_score_margin=_mean(metric.score_margin for metric in metrics),
        worst_case_ndcg_at_k=round(min(metric.ndcg_at_k for metric in metrics), 6),
    )


def _source_key(result: SearchResult) -> str:
    return result.source_entry_id or result.memory_id


def _deduplicate_by_source(results: Sequence[SearchResult]) -> list[SearchResult]:
    unique: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        key = _source_key(result)
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def _discounted_cumulative_gain(grades: Sequence[float]) -> float:
    return sum(((2.0**grade) - 1.0) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def _mean(values: Iterable[float]) -> float:
    return round(fmean(values), 6)
