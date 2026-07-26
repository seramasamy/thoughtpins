"""Deterministic contextual salience for entries, entities, and topics.

Salience is an inspectable ranking prior, not a claim about objective human
importance. It combines repeated evidence, structural role, graph breadth,
source reliability, recency, and an explicit user rating. All signals are
bounded so a frequent but irrelevant name cannot overwhelm an exact query.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

MODEL_VERSION = "salience-v4"

ENTITY_SIGNAL_WEIGHTS: dict[str, float] = {
    "recurrence": 0.15,
    "mention_density": 0.08,
    "structural_role": 0.18,
    "graph_breadth": 0.12,
    "thematic_breadth": 0.10,
    "source_diversity": 0.05,
    "temporal_persistence": 0.06,
    "evidence_quality": 0.10,
    "recency": 0.06,
    "manual_rating": 0.10,
}
ENTRY_SIGNAL_WEIGHTS: dict[str, float] = {
    "content": 0.06,
    "entities": 0.09,
    "topics": 0.07,
    "durable_facts": 0.17,
    "social_context": 0.15,
    "narrative_structure": 0.14,
    "commitments": 0.10,
    "source_prior": 0.06,
    "manual_rating": 0.16,
}


@dataclass(frozen=True)
class SalienceScore:
    score: float
    uncertainty: float
    tier: str
    signals: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    model_version: str = MODEL_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EntitySalienceObservation:
    """Aggregated evidence for one entity inside one user's memory graph."""

    entity_type: str = "concept"
    distinct_entry_count: int = 0
    mention_count: int = 0
    direct_memory_count: int = 0
    supporting_memory_count: int = 0
    relationship_count: int = 0
    relationship_evidence_count: int = 0
    event_count: int = 0
    agency_count: int = 0
    topic_breadth: int = 0
    topic_entropy: float = 0.0
    source_count: int = 0
    temporal_span_days: int = 0
    active_day_count: int = 0
    observed_evidence_count: int = 0
    reported_evidence_count: int = 0
    inferred_evidence_count: int = 0
    user_rating_mean: float | None = None
    user_rating_count: int = 0
    last_seen: date | datetime | str | None = None


@dataclass(frozen=True)
class EntrySalienceObservation:
    """Signals available immediately after one entry is extracted."""

    word_count: int = 0
    entity_count: int = 0
    person_count: int = 0
    topic_count: int = 0
    memory_count: int = 0
    relationship_count: int = 0
    event_count: int = 0
    action_count: int = 0
    decision_count: int = 0
    quote_count: int = 0
    social_dynamic_count: int = 0
    attributed_quote_count: int = 0
    causal_link_count: int = 0
    open_loop_count: int = 0
    high_stakes_count: int = 0
    user_importance: int | None = None
    source_kind: str = "journal"


def score_entity_salience(
    observation: EntitySalienceObservation,
    *,
    as_of: date | None = None,
) -> SalienceScore:
    """Score a person, place, topic, or concept from durable graph evidence.

    The structural-role term is the useful distinction between a protagonist
    and a peripheral character: direct subject facts and agency count more
    than passive co-occurrence. Recurrence and graph breadth then provide the
    series-level signal without making frequency the definition of importance.
    """

    linked_memories = observation.direct_memory_count + observation.supporting_memory_count
    direct_role = _ratio(observation.direct_memory_count, linked_memories)
    agency = _saturating(observation.agency_count, 3.0)
    event_role = _saturating(observation.event_count, 2.0)
    structural_role = _clamp(0.55 * direct_role + 0.25 * agency + 0.20 * event_role)

    recurrence = _saturating(observation.distinct_entry_count, 4.0)
    mention_density = _saturating(observation.mention_count, 5.0)
    graph_breadth = _saturating(
        observation.relationship_count + 0.35 * observation.relationship_evidence_count,
        4.0,
    )
    thematic_breadth = _clamp(0.55 * _saturating(observation.topic_breadth, 3.0) + 0.45 * observation.topic_entropy)
    source_diversity = _saturating(observation.source_count, 3.0)
    temporal_persistence = _clamp(
        0.60 * _saturating(observation.temporal_span_days, 180.0)
        + 0.40 * _saturating(observation.active_day_count, 5.0)
    )
    evidence_quality = _evidence_quality(observation)
    recency = _recency_signal(observation.last_seen, as_of=as_of)
    manual = _manual_signal(observation.user_rating_mean, observation.user_rating_count)

    signals = {
        "recurrence": recurrence,
        "mention_density": mention_density,
        "structural_role": structural_role,
        "graph_breadth": graph_breadth,
        "thematic_breadth": thematic_breadth,
        "source_diversity": source_diversity,
        "temporal_persistence": temporal_persistence,
        "evidence_quality": evidence_quality,
        "recency": recency,
        "manual_rating": manual,
    }
    effective_evidence = _entity_effective_evidence(observation, evidence_quality=evidence_quality)
    signals["effective_evidence"] = _clamp(effective_evidence / 20.0)
    contributions = _weighted_contributions(signals, ENTITY_SIGNAL_WEIGHTS)
    score = _clamp(sum(contributions.values()))
    uncertainty = _uncertainty(effective_evidence)
    return SalienceScore(
        score=round(score, 6),
        uncertainty=round(uncertainty, 6),
        tier=salience_tier(score),
        signals={key: round(value, 6) for key, value in signals.items()},
        contributions={key: round(value, 6) for key, value in contributions.items()},
    )


def score_entry_salience(
    observation: EntrySalienceObservation,
) -> SalienceScore:
    """Score the durability of one note without equating length with value."""

    content = _saturating(observation.word_count, 180.0)
    entity_signal = _saturating(observation.entity_count + observation.person_count, 6.0)
    topic_signal = _saturating(observation.topic_count, 3.0)
    durable_signal = _saturating(
        observation.memory_count
        + 2.0 * observation.decision_count
        + 1.5 * observation.action_count
        + 0.5 * observation.quote_count,
        6.0,
    )
    social_signal = _saturating(
        observation.event_count + observation.relationship_count + observation.social_dynamic_count,
        5.0,
    )
    narrative_structure = _saturating(
        (1.25 * observation.attributed_quote_count)
        + (0.85 * observation.causal_link_count)
        + (0.75 * observation.open_loop_count)
        + (0.50 * observation.high_stakes_count),
        5.0,
    )
    source_signal = 1.0 if observation.source_kind == "journal" else 0.78
    manual = _entry_manual_signal(observation.user_importance)
    evidence_count = (
        observation.entity_count
        + observation.memory_count
        + observation.relationship_count
        + observation.event_count
        + observation.attributed_quote_count
        + observation.causal_link_count
        + observation.open_loop_count
    )
    signals: dict[str, float] = {
        "content": content,
        "entities": entity_signal,
        "topics": topic_signal,
        "durable_facts": durable_signal,
        "social_context": social_signal,
        "narrative_structure": narrative_structure,
        "commitments": _saturating(observation.action_count + observation.decision_count, 3.0),
        "source_prior": source_signal,
        "manual_rating": manual,
        "evidence_count": _clamp(evidence_count / 20.0),
    }
    return score_entry_signals(signals)


def rescore_entry_salience(
    signals: Mapping[str, float],
    *,
    user_importance: int | None,
) -> SalienceScore:
    """Reapply an explicit rating without reconstructing private entry text.

    Persisted normalized signals are sufficient for this operation. This keeps
    star updates deterministic and avoids decrypting a private journal entry.
    """

    updated = {key: _clamp(value) for key, value in signals.items()}
    updated["manual_rating"] = _entry_manual_signal(user_importance)
    return score_entry_signals(updated)


def score_entry_signals(signals: Mapping[str, float]) -> SalienceScore:
    """Combine normalized entry signals using the versioned v3 weights."""

    normalized = {key: _clamp(value) for key, value in signals.items()}
    contributions = _weighted_contributions(normalized, ENTRY_SIGNAL_WEIGHTS)
    score = _clamp(sum(contributions.values()))
    evidence_count = round(normalized.get("evidence_count", 0.0) * 20.0)
    return SalienceScore(
        score=round(score, 6),
        uncertainty=round(_uncertainty(evidence_count), 6),
        tier=salience_tier(score),
        signals={key: round(value, 6) for key, value in normalized.items()},
        contributions={key: round(value, 6) for key, value in contributions.items()},
    )


def memory_type_salience(memory_type: str | None) -> float:
    """Give durable facts a small prior when query relevance is otherwise tied."""

    return {
        "decision": 0.95,
        "commitment": 0.94,
        "future_plan": 0.91,
        "user_action": 0.88,
        "relationship_update": 0.87,
        "social_dynamic": 0.84,
        "quote": 0.82,
        "event": 0.80,
        "fact": 0.78,
        "thought": 0.76,
        "observation": 0.74,
        "progress_update": 0.72,
        "source_excerpt": 0.66,
    }.get((memory_type or "").strip().lower(), 0.70)


def salience_tier(score: float) -> str:
    if score >= 0.76:
        return "central"
    if score >= 0.54:
        return "notable"
    if score >= 0.30:
        return "supporting"
    return "background"


def source_kind(source: str | None) -> str:
    value = (source or "").strip().lower()
    if any(token in value for token in ("document", "article", "book", "library", "obsidian", "vault", "source")):
        return "document"
    return "journal"


def _manual_signal(mean_rating: float | None, rating_count: int) -> float:
    if mean_rating is None or rating_count <= 0:
        return 0.5
    normalized = _clamp((float(mean_rating) - 1.0) / 4.0)
    confidence = _saturating(rating_count, 2.0)
    return _clamp(0.5 + ((0.10 + 0.90 * normalized) - 0.5) * confidence)


def _entry_manual_signal(value: int | None) -> float:
    if value is None:
        return 0.5
    return _clamp(0.10 + 0.90 * ((float(value) - 1.0) / 4.0))


def _evidence_quality(observation: EntitySalienceObservation) -> float:
    total = (
        observation.observed_evidence_count + observation.reported_evidence_count + observation.inferred_evidence_count
    )
    if total <= 0:
        return 0.35
    return _clamp(
        (
            1.0 * observation.observed_evidence_count
            + 0.78 * observation.reported_evidence_count
            + 0.45 * observation.inferred_evidence_count
        )
        / total
    )


def _recency_signal(value: date | datetime | str | None, *, as_of: date | None) -> float:
    observed = _coerce_date(value)
    if observed is None:
        return 0.35
    reference = as_of or date.today()
    age_days = max(0, (reference - observed).days)
    return _clamp(math.exp(-age_days / 730.0))


def _coerce_date(value: date | datetime | str | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _entity_effective_evidence(
    observation: EntitySalienceObservation,
    *,
    evidence_quality: float,
) -> float:
    """Estimate independent support without treating duplicate mentions as samples."""

    independent = (
        observation.distinct_entry_count + (0.50 * observation.active_day_count) + (0.35 * observation.source_count)
    )
    structural = (
        (0.35 * observation.direct_memory_count)
        + (0.20 * observation.supporting_memory_count)
        + (0.25 * observation.relationship_evidence_count)
        + (0.40 * observation.event_count)
    )
    structural_cap = 2.0 * max(1.0, independent)
    duplicate_mentions = max(0, observation.mention_count - observation.distinct_entry_count)
    duplicate_credit = min(1.0, math.log1p(duplicate_mentions) / 6.0)
    return max(0.0, evidence_quality * (independent + min(structural, structural_cap) + duplicate_credit))


def _uncertainty(effective_evidence: float) -> float:
    """Return normalized posterior spread under a symmetric Beta prior.

    The expression is one at zero evidence and contracts as effective,
    independent support accumulates. It is an epistemic diagnostic, not a
    calibrated probability that a memory is true.
    """

    return _clamp(math.sqrt(3.0 / (3.0 + max(0.0, float(effective_evidence)))))


def _weighted_contributions(
    signals: Mapping[str, float],
    weights: Mapping[str, float],
) -> dict[str, float]:
    return {name: weight * _clamp(signals.get(name, 0.0)) for name, weight in weights.items()}


def _saturating(value: float, scale: float) -> float:
    if value <= 0:
        return 0.0
    return _clamp(1.0 - math.exp(-float(value) / max(scale, 0.001)))


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp(float(numerator) / float(denominator))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
