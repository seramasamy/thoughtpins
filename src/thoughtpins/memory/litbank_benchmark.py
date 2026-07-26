"""Human speaker-attribution evaluation over LitBank quotation annotations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any

from thoughtpins.memory.benchmark_datasets import BenchmarkPartition, benchmark_partition
from thoughtpins.memory.benchmark_retrieval import AggregateRankMetrics, CaseRank, aggregate_case_ranks
from thoughtpins.memory.ranking import DEFAULT_RANKING_POLICY, RankingPolicy, rerank_results
from thoughtpins.memory.search_types import SearchResult


@dataclass(frozen=True)
class LitBankReport:
    partition: str
    works: int
    speaker_queries: int
    quote_candidates: int
    minor_speaker_queries: int
    all_speakers: AggregateRankMetrics
    minor_speakers: AggregateRankMetrics

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["all_speakers"] = self.all_speakers.as_dict()
        payload["minor_speakers"] = self.minor_speakers.as_dict()
        return payload


@dataclass(frozen=True)
class _Quote:
    quote_id: str
    text: str
    speaker_id: str

    @property
    def speaker_name(self) -> str:
        return self.speaker_id.rsplit("-", 1)[0].replace("_", " ").strip()


def evaluate_litbank(
    quotations_dir: Path,
    *,
    partition: BenchmarkPartition | None = None,
    policy: RankingPolicy = DEFAULT_RANKING_POLICY,
    max_works: int | None = None,
) -> LitBankReport:
    all_cases: list[CaseRank] = []
    minor_cases: list[CaseRank] = []
    work_count = 0
    candidate_count = 0
    for annotation_path in sorted(quotations_dir.glob("*.ann")):
        quotes = _read_quotes(annotation_path)
        if not quotes:
            continue
        work_id = annotation_path.stem
        work_cases, work_minor_cases = _evaluate_work(work_id, quotes, partition, policy)
        if not work_cases:
            continue
        all_cases.extend(work_cases)
        minor_cases.extend(work_minor_cases)
        candidate_count += len(quotes)
        work_count += 1
        if max_works is not None and work_count >= max_works:
            break
    return LitBankReport(
        partition=partition or "all",
        works=work_count,
        speaker_queries=len(all_cases),
        quote_candidates=candidate_count,
        minor_speaker_queries=len(minor_cases),
        all_speakers=aggregate_case_ranks(all_cases),
        minor_speakers=aggregate_case_ranks(minor_cases),
    )


def _read_quotes(path: Path) -> list[_Quote]:
    quote_text: dict[str, str] = {}
    attribution: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("\t", 6)
        if len(fields) >= 7 and fields[0] == "QUOTE":
            quote_text[fields[1]] = fields[6].strip()
        elif len(fields) >= 3 and fields[0] == "ATTRIB":
            attribution[fields[1]] = fields[2].strip()
    return [
        _Quote(quote_id=quote_id, text=text, speaker_id=attribution[quote_id])
        for quote_id, text in quote_text.items()
        if attribution.get(quote_id)
    ]


def _evaluate_work(
    work_id: str,
    quotes: list[_Quote],
    partition: BenchmarkPartition | None,
    policy: RankingPolicy,
) -> tuple[list[CaseRank], list[CaseRank]]:
    by_speaker: dict[str, set[str]] = {}
    for quote in quotes:
        by_speaker.setdefault(quote.speaker_id, set()).add(quote.quote_id)
    frequency_cutoff = median(len(ids) for ids in by_speaker.values())
    title = _work_title(work_id)
    all_cases: list[CaseRank] = []
    minor_cases: list[CaseRank] = []
    for speaker_id, relevant_ids in sorted(by_speaker.items()):
        stable_id = f"{work_id}:{speaker_id}"
        if partition and benchmark_partition(stable_id) != partition:
            continue
        speaker = speaker_id.rsplit("-", 1)[0].replace("_", " ").strip()
        query = f"What did {speaker} say in {title}?"
        candidates = [_quote_candidate(work_id, title, quote) for quote in quotes]
        ranked = rerank_results(candidates, query=query, limit=min(10, len(candidates)), policy=policy)
        case = CaseRank(
            relevant_ids=frozenset(relevant_ids),
            ranked_ids=tuple(item.source_entry_id for item in ranked),
        )
        all_cases.append(case)
        if len(relevant_ids) <= frequency_cutoff:
            minor_cases.append(case)
    return all_cases, minor_cases


def _quote_candidate(work_id: str, title: str, quote: _Quote) -> SearchResult:
    return SearchResult(
        memory_id=f"litbank:{work_id}:{quote.quote_id}",
        text=quote.text,
        memory_type="quote",
        local_date="",
        confidence="attributed_statement",
        sensitivity="personal",
        source_entry_id=quote.quote_id,
        score=0.5,
        entity_names=[quote.speaker_name],
        source_kind="document",
        source_title=title,
        evidence_text=quote.text,
        source_provenance=f"litbank:{work_id}",
        evidence_metadata={
            "attributed_to": quote.speaker_name,
            "people_involved": [quote.speaker_name],
            "epistemic_status": "attributed_statement",
        },
        retrieval_sources=["human_annotation"],
    )


def _work_title(work_id: str) -> str:
    value = work_id.removesuffix("_brat")
    _, separator, title = value.partition("_")
    return (title if separator else value).replace("_", " ").strip().title()
