"""Large deterministic benchmark for contemporary social-memory settings."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from statistics import fmean

from thoughtpins.memory.ranking import DEFAULT_RANKING_POLICY, RankingPolicy, rerank_results
from thoughtpins.memory.search_types import SearchResult
from thoughtpins.memory.social_relevance import analyze_social_query, score_social_evidence

_SETTINGS = (
    (
        "high_school",
        "Westbridge Library",
        "rehearsal",
        "an older student mocked the audition draft",
        "the director offered a private retry",
    ),
    (
        "prep_school",
        "Hawthorne Commons",
        "debate dinner",
        "the captain changed the speaking order",
        "the team restored the original order",
    ),
    (
        "coastal_social",
        "Harbor House",
        "bonfire",
        "the storm moved the boat launch",
        "everyone regrouped at the marina",
    ),
    (
        "college",
        "Juniper Hall",
        "student show",
        "the curator lost the lighting slot",
        "a later installation slot opened",
    ),
    (
        "finance",
        "Marlow Club",
        "investor dinner",
        "compliance needed the revised data room log",
        "legal approved a limited follow-up",
    ),
    (
        "consulting",
        "Aster Hotel",
        "client workshop",
        "the sponsor rejected the first operating model",
        "the team tested a smaller pilot",
    ),
    (
        "startup",
        "Foundry Cafe",
        "product review",
        "customers trusted manual recovery more than animation",
        "the roadmap moved restore drills first",
    ),
    (
        "artist",
        "Celia Studio",
        "gallery review",
        "the blue canvases formed the strongest series",
        "the exhibition became more focused",
    ),
    (
        "writer",
        "Lantern Books",
        "reading",
        "the editor wanted the narrator's doubt preserved",
        "the final chapter kept the ambiguity",
    ),
    ("music", "Echo Room", "sound check", "the bridge crowded the lead vocal", "the band removed one guitar layer"),
    ("nightlife", "Lumen Bar", "birthday drinks", "the private room closed early", "the group moved to the garden"),
    (
        "networking",
        "Goodwin Hall",
        "founder mixer",
        "the buyer cared about audit evidence",
        "a technical diligence call was scheduled",
    ),
    (
        "family",
        "Willow Kitchen",
        "Sunday dinner",
        "the travel dates conflicted with the reunion",
        "the family shifted the reunion one week",
    ),
    ("dating", "Koyo Ramen", "date night", "both people wanted phones away at dinner", "they made a no-phones rule"),
    (
        "travel",
        "Atlas Hotel",
        "arrival",
        "the rail strike cancelled the morning train",
        "the route changed to the ferry",
    ),
    (
        "community",
        "River Arts Center",
        "volunteer meeting",
        "the grant required a public workshop",
        "the group added a free Saturday session",
    ),
)
_NAMES = (
    "Ava",
    "Sam",
    "Nora",
    "Eli",
    "Maya",
    "Daniel",
    "Priya",
    "Leo",
    "Celia",
    "Julian",
    "Iris",
    "Theo",
    "Amara",
    "Noah",
    "Sofia",
    "Miles",
    "Lena",
    "Ravi",
    "Elena",
    "Marcus",
    "Toya",
    "Quinn",
    "Nadia",
    "Owen",
)


@dataclass(frozen=True)
class SocialBenchmarkSummary:
    case_count: int
    settings: int
    recall_at_1: float
    recall_at_3: float
    mean_reciprocal_rank: float
    requested_facet_coverage: float
    attribution_retention_rate: float
    orphan_uncertain_claim_rate: float
    deterministic_replay: bool

    def as_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


def run_social_benchmark(
    *,
    case_count: int = 5_000,
    seed: int = 20260721,
    policy: RankingPolicy = DEFAULT_RANKING_POLICY,
) -> SocialBenchmarkSummary:
    if case_count <= 0:
        raise ValueError("case_count must be positive")
    rng = random.Random(seed)
    ranks: list[int] = []
    coverage: list[float] = []
    attribution_hits = 0
    orphan_uncertain = 0
    replay_ok = True
    seen_settings: set[str] = set()

    for index in range(case_count):
        setting = _SETTINGS[index % len(_SETTINGS)]
        seen_settings.add(setting[0])
        speaker, subject, decoy_person = rng.sample(_NAMES, 3)
        query, candidates, target_id = _case(index, setting, speaker, subject, decoy_person, rng)
        ranked = rerank_results(candidates, query=query, limit=5, policy=policy)
        rank = next((position for position, item in enumerate(ranked, start=1) if item.memory_id == target_id), 6)
        ranks.append(rank)

        intent = analyze_social_query(query)
        selected_facets = set().union(*(score_social_evidence(item, intent).facets for item in ranked[:3]))
        coverage.append(len(intent.facets & selected_facets) / max(1, len(intent.facets)))
        target = next((item for item in ranked if item.memory_id == target_id), None)
        if target and target.evidence_metadata.get("attributed_to") == speaker:
            attribution_hits += 1
        top_features = score_social_evidence(ranked[0], intent)
        if top_features.factualization_risk > 0:
            orphan_uncertain += 1

        if index < 200:
            replay_candidates = [_copy_candidate(item) for item in candidates]
            replay = rerank_results(replay_candidates, query=query, limit=5, policy=policy)
            replay_ok = replay_ok and [item.memory_id for item in ranked] == [item.memory_id for item in replay]

    return SocialBenchmarkSummary(
        case_count=case_count,
        settings=len(seen_settings),
        recall_at_1=_rate(ranks, 1),
        recall_at_3=_rate(ranks, 3),
        mean_reciprocal_rank=round(fmean(1.0 / rank for rank in ranks), 6),
        requested_facet_coverage=round(fmean(coverage), 6),
        attribution_retention_rate=round(attribution_hits / case_count, 6),
        orphan_uncertain_claim_rate=round(orphan_uncertain / case_count, 6),
        deterministic_replay=replay_ok,
    )


def _case(index, setting, speaker, subject, decoy_person, rng):
    domain, place, event, reason, outcome = setting
    target_id = f"case:{index}:target"
    status = "hearsay_from_person" if index % 3 == 0 else "user_reported"
    query = (
        f"what did {speaker} say about {subject} at {place}, why did it happen, and what followed?"
        if index % 3
        else f"what rumor did {speaker} share about {subject} at {place} and what happened afterward?"
    )
    target_text = f"At {place}, {speaker} said {subject} missed the {event} because {reason}; afterward {outcome}."
    target = _candidate(
        target_id,
        0.68,
        target_text,
        status=status,
        metadata={
            "attributed_to": speaker,
            "people_involved": [speaker, subject],
            "place": place,
            "motivation": reason,
            "consequence": outcome,
            "epistemic_status": status,
            "claim_status": "uncertain" if status == "hearsay_from_person" else "active",
            "social_stakes": "high" if domain in {"high_school", "prep_school", "finance", "dating"} else "medium",
        },
    )
    decoys = [
        _candidate(
            f"case:{index}:same-place",
            0.71,
            f"{decoy_person} attended the {event} at {place}.",
            metadata={"place": place, "people_involved": [decoy_person]},
        ),
        _candidate(
            f"case:{index}:same-speaker",
            0.70,
            f"{speaker} discussed an unrelated schedule with {decoy_person}.",
            metadata={"attributed_to": speaker, "people_involved": [speaker, decoy_person]},
        ),
        _candidate(
            f"case:{index}:orphan",
            0.69,
            f"{subject} missed the {event} because {reason}.",
            status="hearsay_from_person",
            metadata={"epistemic_status": "hearsay_from_person"},
        ),
        _candidate(
            f"case:{index}:cause", 0.66, f"The recorded reason was that {reason}.", metadata={"motivation": reason}
        ),
        _candidate(f"case:{index}:outcome", 0.65, f"Afterward, {outcome}.", metadata={"consequence": outcome}),
        _candidate(
            f"case:{index}:old",
            0.74,
            f"A highly rated older note mentioned {speaker} and {subject} without describing the event.",
        ),
    ]
    decoys[-1].user_importance = 5
    rng.shuffle(decoys)
    return query, [*decoys, target], target_id


def _candidate(memory_id: str, score: float, text: str, *, status="observed_by_user", metadata=None):
    return SearchResult(
        memory_id=memory_id,
        text=text,
        memory_type="quote" if (metadata or {}).get("attributed_to") else "observation",
        local_date="2026-07-21",
        confidence=status,
        sensitivity="personal",
        source_entry_id=memory_id,
        score=score,
        evidence_text=text,
        evidence_metadata=dict(metadata or {}),
        retrieval_sources=["benchmark"],
        source_ranks={"benchmark": 1},
    )


def _copy_candidate(item: SearchResult) -> SearchResult:
    copied = _candidate(
        item.memory_id,
        float(item.ranking_signals.get("base", item.score)),
        item.text,
        status=item.confidence,
        metadata=item.evidence_metadata,
    )
    copied.user_importance = item.user_importance
    return copied


def _rate(ranks: list[int], cutoff: int) -> float:
    return round(sum(1 for rank in ranks if rank <= cutoff) / len(ranks), 6)
