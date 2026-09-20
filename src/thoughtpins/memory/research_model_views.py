"""Matched public-evidence views and strict offline model-response application."""

from __future__ import annotations

import hashlib
import json
import math

from thoughtpins.memory.benchmark_model_ranking import (
    SessionRankingCandidate,
    apply_session_ranking,
    session_ranking_messages,
)
from thoughtpins.memory.research_data import ResearchSource
from thoughtpins.memory.research_retrieval import Representation


def evidence_view(
    query_id: str,
    question: str,
    sources: dict[str, ResearchSource],
    baseline: list[str],
    *,
    as_of: str = "",
    byte_budget: int | None = 120000,
    permutation: int = 0,
) -> dict:
    if not baseline or len(set(baseline)) != len(baseline):
        raise ValueError("Expected a nonempty unique baseline source pool")
    ordered = sorted(
        baseline, key=lambda sid: hashlib.sha256(f"20260919:{query_id}:{permutation}:{sid}".encode()).hexdigest()
    )
    texts = {sid: sources[sid].text for sid in ordered}
    original_bytes = sum(len(text.encode()) for text in texts.values())
    truncated = []
    if byte_budget is not None and original_bytes > byte_budget:
        if byte_budget // len(ordered) < 128:
            raise ValueError("Context budget too small for an evidence source")
        rep = Representation(max_bytes=byte_budget // len(ordered))
        for sid in ordered:
            projected = rep.render(texts[sid])
            if projected != texts[sid]:
                truncated.append(sid)
            texts[sid] = projected
    question_text = (
        (f"Question date: {as_of}\n" if as_of else "Full-history retrieval; no as-of date supplied.\n")
        + "Personal memory question: "
        + question
    )
    candidates = tuple(SessionRankingCandidate(sources[sid].date, texts[sid]) for sid in ordered)
    return {
        "messages": session_ranking_messages(question_text, candidates),
        "candidate_ids": ordered,
        "baseline_ids": baseline,
        "question": question_text,
        "documents": [f"Session date: {sources[sid].date}\n{texts[sid]}" for sid in ordered],
        "original_evidence_bytes": original_bytes,
        "evidence_bytes": sum(len(text.encode()) for text in texts.values()),
        "truncated_sources": truncated,
        "byte_budget": byte_budget,
        "permutation": permutation,
    }


def response_ranking(
    record: dict, *, candidate_ids: list[str], baseline_ids: list[str]
) -> tuple[list[str], str | None]:
    content = record.get("content")
    completed = record.get("status") == "ok"
    reason = None
    if record.get("kind") == "chat":
        completed = completed and record.get("finish_reason") == "stop"
        if not completed:
            reason = record.get("status") if record.get("status") != "ok" else "incomplete_completion"
    elif record.get("kind") == "rerank":
        data = record.get("data")
        if not isinstance(data, list) or any(
            not isinstance(row, dict)
            or type(row.get("index")) is not int
            or type(row.get("relevance_score")) not in (int, float)
            or not math.isfinite(row["relevance_score"])
            for row in data
        ):
            completed = False
        else:
            content = json.dumps({"ranking": [row["index"] for row in data]})
        if not completed:
            reason = "invalid_or_failed_rerank"
    else:
        completed = False
        reason = "unknown_response_kind"
    result = apply_session_ranking(
        content, candidate_ids=tuple(candidate_ids), baseline_ids=tuple(baseline_ids), completed=completed
    )
    return list(result.ranked_ids), reason or ("invalid_full_permutation" if result.used_fallback else None)
