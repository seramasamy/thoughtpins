"""Retrieval-only evaluation over the permissively licensed LongMemEval split."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from thoughtpins.memory.benchmark_datasets import BenchmarkPartition, benchmark_partition
from thoughtpins.memory.benchmark_retrieval import (
    AggregateRankMetrics,
    CaseRank,
    aggregate_case_ranks,
    rank_documents_bm25,
)
from thoughtpins.memory.ranking import DEFAULT_RANKING_POLICY, RankingPolicy, rerank_results
from thoughtpins.memory.search_types import SearchResult

_DATE_RE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})")


@dataclass(frozen=True)
class LongMemEvalReport:
    partition: str
    evaluated_questions: int
    abstention_questions: int
    baseline: AggregateRankMetrics
    thoughtpins: AggregateRankMetrics
    by_question_type: dict[str, AggregateRankMetrics]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["baseline"] = self.baseline.as_dict()
        payload["thoughtpins"] = self.thoughtpins.as_dict()
        payload["by_question_type"] = {
            name: metrics.as_dict() for name, metrics in sorted(self.by_question_type.items())
        }
        return payload


def evaluate_longmemeval(
    dataset_path: Path,
    *,
    partition: BenchmarkPartition | None = None,
    policy: RankingPolicy = DEFAULT_RANKING_POLICY,
    max_cases: int | None = None,
) -> LongMemEvalReport:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("LongMemEval root must be a list")

    baseline_cases: list[CaseRank] = []
    ranked_cases: list[CaseRank] = []
    by_type: dict[str, list[CaseRank]] = {}
    abstentions = 0
    for raw in payload:
        case = _parse_case(raw)
        if partition and benchmark_partition(case.question_id) != partition:
            continue
        if not case.answer_session_ids:
            abstentions += 1
            continue
        baseline, ranked = _evaluate_case(case, policy)
        baseline_cases.append(baseline)
        ranked_cases.append(ranked)
        by_type.setdefault(case.question_type, []).append(ranked)
        if max_cases is not None and len(ranked_cases) >= max_cases:
            break

    return LongMemEvalReport(
        partition=partition or "all",
        evaluated_questions=len(ranked_cases),
        abstention_questions=abstentions,
        baseline=aggregate_case_ranks(baseline_cases),
        thoughtpins=aggregate_case_ranks(ranked_cases),
        by_question_type={name: aggregate_case_ranks(cases) for name, cases in by_type.items()},
    )


@dataclass(frozen=True)
class _LongMemEvalCase:
    question_id: str
    question_type: str
    question: str
    question_date: str
    answer_session_ids: frozenset[str]
    session_ids: tuple[str, ...]
    session_dates: tuple[str, ...]
    session_texts: tuple[str, ...]


def _parse_case(raw: Any) -> _LongMemEvalCase:
    if not isinstance(raw, dict):
        raise ValueError("LongMemEval case must be an object")
    session_ids = tuple(str(value) for value in raw.get("haystack_session_ids") or ())
    session_dates = tuple(str(value) for value in raw.get("haystack_dates") or ())
    sessions = raw.get("haystack_sessions") or ()
    if not isinstance(sessions, list) or len(session_ids) != len(sessions) or len(session_dates) != len(sessions):
        raise ValueError(f"LongMemEval case {raw.get('question_id')} has misaligned session arrays")
    return _LongMemEvalCase(
        question_id=str(raw.get("question_id") or ""),
        question_type=str(raw.get("question_type") or "unknown"),
        question=str(raw.get("question") or ""),
        question_date=str(raw.get("question_date") or ""),
        answer_session_ids=frozenset(str(value) for value in raw.get("answer_session_ids") or ()),
        session_ids=session_ids,
        session_dates=session_dates,
        session_texts=tuple(_session_text(session) for session in sessions),
    )


def _session_text(session: Any) -> str:
    if not isinstance(session, list):
        return ""
    turns: list[str] = []
    for turn in session:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "speaker").strip()
        content = str(turn.get("content") or "").strip()
        if content:
            turns.append(f"{role}: {content}")
    return "\n".join(turns)


def _evaluate_case(case: _LongMemEvalCase, policy: RankingPolicy) -> tuple[CaseRank, CaseRank]:
    lexical_order = rank_documents_bm25(case.question, list(case.session_texts))
    baseline_ids = tuple(case.session_ids[index] for index, _score in lexical_order[:10])
    candidates = [_candidate(case, index, score, rank) for rank, (index, score) in enumerate(lexical_order, start=1)]
    ranked = rerank_results(
        candidates,
        query=case.question,
        limit=min(10, len(candidates)),
        policy=policy,
        as_of_date=_parse_date(case.question_date),
    )
    relevant = case.answer_session_ids
    return (
        CaseRank(relevant_ids=relevant, ranked_ids=baseline_ids),
        CaseRank(relevant_ids=relevant, ranked_ids=tuple(item.source_entry_id for item in ranked)),
    )


def _candidate(case: _LongMemEvalCase, index: int, score: float, rank: int) -> SearchResult:
    session_id = case.session_ids[index]
    date_text = case.session_dates[index]
    return SearchResult(
        memory_id=f"longmemeval:{case.question_id}:{session_id}",
        text=case.session_texts[index],
        memory_type="conversation_session",
        local_date=_iso_date(date_text),
        confidence="user_reported",
        sensitivity="personal",
        source_entry_id=session_id,
        score=score,
        evidence_text=case.session_texts[index],
        evidence_metadata={"session_date": date_text},
        retrieval_sources=["benchmark_bm25"],
        source_ranks={"benchmark_bm25": rank},
    )


def _iso_date(value: str) -> str:
    match = _DATE_RE.search(value)
    return "-".join(match.groups()) if match else ""


def _parse_date(value: str) -> date | None:
    rendered = _iso_date(value)
    return date.fromisoformat(rendered) if rendered else None
