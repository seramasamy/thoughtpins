"""Pure ranking policy, score fusion, and context diversification.

Candidate generation belongs to :mod:`thoughtpins.memory.search`. Keeping the
ranking stage pure makes its assumptions measurable: an evaluation can replay
the same candidate pool under controlled ablations without querying a provider
again or changing tenant-scoped retrieval behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
from datetime import date

from thoughtpins.importance import importance_bonus
from thoughtpins.memory.ranking_evidence import build_ranking_evidence
from thoughtpins.memory.salience import memory_type_salience
from thoughtpins.memory.search_analysis import (
    _analyze_query,
    _lexical_signal,
    _phrase_score,
    _proximity_score,
    _token_sequence,
    _tokens,
)
from thoughtpins.memory.search_types import QueryAnalysis, SearchResult
from thoughtpins.memory.social_relevance import (
    SocialQueryIntent,
    analyze_social_query,
    candidate_facets,
    score_social_evidence,
)
from thoughtpins.memory.temporal_relevance import (
    TemporalWindow,
    parse_temporal_window,
    temporal_window_match,
)


@dataclass(frozen=True)
class RankingWeights:
    """Immutable, bounded coefficients for score fusion.

    Retrieval evidence remains dominant. Personal importance and social
    structure are constrained to breaking close ties rather than manufacturing
    relevance that candidate generation did not find.

    Every number the scoring function multiplies by lives here, including the
    small structural priors. Scattering some of them as literals inside
    :func:`_calibrated_score` would leave half the model's hyperparameters
    unvalidated and invisible to an ablation, which is exactly the failure mode
    the bounds below exist to prevent.
    """

    base: float = 0.68
    lexical: float = 0.18
    phrase: float = 0.05
    proximity: float = 0.04
    reciprocal_rank: float = 1.25
    relevance: float = 0.93
    contextual_salience: float = 0.02
    memory_type_salience: float = 0.02
    temporal_query: float = 0.06
    social_utility: float = 0.15
    factualization_penalty: float = 0.035

    # Agreement between independent retrievers, saturating: the second channel
    # that finds a candidate is strong evidence, the fifth adds little. Capped
    # so consensus can break a tie but never outrank the evidence itself.
    consensus_scale: float = 0.018
    consensus_cap: float = 0.045

    # A retrieved document was deliberately saved to be read again, and a graph
    # hit survived entity resolution. Both are weak positive priors.
    document_kind_prior: float = 0.015
    graph_prior: float = 0.015

    # Neutral points for the two salience signals. A candidate at its neutral
    # value contributes nothing, so the priors shift ranking only when the
    # signal actually departs from the population default.
    contextual_salience_neutral: float = 0.5
    memory_type_salience_neutral: float = 0.70

    # Stated importance is a preference signal, not a truth score. On a socially
    # specific question it is gated by how well the candidate matches the people
    # asked about, with floors so a strong personal rating is damped rather than
    # erased.
    importance_gate_floor: float = 0.05
    identity_match_floor: float = 0.25

    def __post_init__(self) -> None:
        # Upper bounds encode intent, not arithmetic: each is the point past
        # which that term could overturn retrieval evidence on its own.
        limits = {
            "base": 1.0,
            "lexical": 0.5,
            "phrase": 0.25,
            "proximity": 0.25,
            "reciprocal_rank": 3.0,
            "relevance": 1.0,
            "contextual_salience": 0.1,
            "memory_type_salience": 0.1,
            "temporal_query": 0.2,
            "social_utility": 0.3,
            "factualization_penalty": 0.15,
            "consensus_scale": 0.1,
            "consensus_cap": 0.15,
            "document_kind_prior": 0.1,
            "graph_prior": 0.1,
            "contextual_salience_neutral": 1.0,
            "memory_type_salience_neutral": 1.0,
            "importance_gate_floor": 1.0,
            "identity_match_floor": 1.0,
        }
        for field_name, upper_bound in limits.items():
            value = getattr(self, field_name)
            if not math.isfinite(value) or not 0.0 <= value <= upper_bound:
                raise ValueError(f"{field_name} weight must be between 0 and {upper_bound}")
        if set(limits) != {f.name for f in fields(self)}:
            # A new coefficient added without a bound would silently skip
            # validation, so the mismatch is a programming error, not input.
            missing = {f.name for f in fields(self)} - set(limits)
            raise AssertionError(f"ranking coefficients without a declared bound: {sorted(missing)}")


DEFAULT_RANKING_WEIGHTS = RankingWeights()


@dataclass(frozen=True)
class RankingPolicy:
    """Feature switches for a reproducible ranking experiment.

    These switches are intentionally coarse. They support useful ablations
    without turning production ranking into a bag of runtime tuning knobs.
    """

    name: str = "social-episodic-v2"
    weights: RankingWeights = DEFAULT_RANKING_WEIGHTS
    lexical_evidence: bool = True
    rank_fusion: bool = True
    structural_priors: bool = True
    salience_priors: bool = True
    social_evidence: bool = True
    diversity_lambda: float | None = 0.82
    adaptive_diversity: bool = True
    aspect_coverage: bool = True
    narrative_coverage: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("ranking policy name must not be empty")
        if self.diversity_lambda is not None and not 0.0 <= self.diversity_lambda <= 1.0:
            raise ValueError("diversity_lambda must be between 0 and 1")


DEFAULT_RANKING_POLICY = RankingPolicy()


@dataclass
class _RankingContext:
    """Everything a rerank needs that does not vary per candidate.

    Reranking touches each candidate several times: once to score, then again
    in diversification and each coverage repair. Query interpretation and a
    candidate's own facets are invariant across those passes, so computing them
    inside the loops meant re-deriving the same answers tens of times per
    query. This holds them once.

    Not frozen: ``facets`` memoises on access. It is created per rerank call and
    never shared between them, so the mutation stays local to one query.
    """

    analysis: QueryAnalysis
    as_of_date: date
    social_intent: SocialQueryIntent
    temporal_window: TemporalWindow | None
    _facets: dict[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, query: str, as_of_date: date) -> _RankingContext:
        analysis = _analyze_query(query)
        return cls(
            analysis=analysis,
            as_of_date=as_of_date,
            social_intent=analyze_social_query(analysis.raw),
            temporal_window=parse_temporal_window(analysis.raw, as_of=as_of_date),
        )

    def facets(self, candidate: SearchResult) -> frozenset[str]:
        """This candidate's social facets, derived at most once per rerank."""
        cached = self._facets.get(candidate.memory_id)
        if cached is None:
            cached = candidate_facets(candidate)
            self._facets[candidate.memory_id] = cached
        return cached

    def requested_facets(self) -> set[str]:
        return set(self.social_intent.facets)


def rerank_results(
    results: list[SearchResult],
    *,
    query: str,
    limit: int,
    policy: RankingPolicy = DEFAULT_RANKING_POLICY,
    as_of_date: date | None = None,
) -> list[SearchResult]:
    """Fuse retrieval channels and select a compact evidence set."""
    if not results or limit <= 0:
        return []
    context = _RankingContext.build(query, as_of_date or date.today())
    for result in results:
        result.score = _calibrated_score(result, context, policy)

    ranked = sorted(results, key=lambda result: (result.score, result.local_date), reverse=True)
    adaptive_skip = policy.adaptive_diversity and not _needs_diversification(ranked, context)
    if policy.diversity_lambda is None or adaptive_skip:
        selected = ranked[:limit]
        if not policy.aspect_coverage:
            return _ensure_narrative_coverage(selected, ranked, context, policy)
        token_cache = {
            candidate.memory_id: _tokens(f"{candidate.text} {candidate.evidence_text}") for candidate in ranked
        }
        selected = _ensure_query_aspect_coverage(selected, ranked, token_cache, context, limit)
        return _ensure_narrative_coverage(selected, ranked, context, policy)
    return _maximal_marginal_relevance(ranked, limit, context, policy)


def _needs_diversification(candidates: list[SearchResult], context: _RankingContext) -> bool:
    """Use coverage repair only when the pool contains distinct evidence views."""
    retrieval_channels = {source for candidate in candidates for source in candidate.retrieval_sources}
    if len(retrieval_channels) > 1:
        return True
    source_keys = [candidate.source_entry_id or candidate.memory_id for candidate in candidates]
    if len(set(source_keys)) < len(source_keys):
        return True

    requested = context.requested_facets()
    if not requested:
        return False
    facet_profiles = {
        matched for candidate in candidates if (matched := frozenset(context.facets(candidate) & requested))
    }
    return len(facet_profiles) > 1


def clone_candidates_for_rerank(results: list[SearchResult]) -> list[SearchResult]:
    """Clone scored candidates and restore their pre-fusion score.

    ``search`` records the bounded channel score as ``ranking_signals.base``.
    Replaying from that value avoids compounding one ranking policy on another.
    """
    clones: list[SearchResult] = []
    for result in results:
        base = float(result.ranking_signals.get("base", result.score))
        clones.append(
            replace(
                result,
                score=base,
                entity_names=list(result.entity_names),
                retrieval_sources=list(result.retrieval_sources),
                source_ranks=dict(result.source_ranks),
                ranking_signals={},
                ranking_policy="candidate",
            )
        )
    return clones


def _calibrated_score(
    result: SearchResult,
    context: _RankingContext,
    policy: RankingPolicy,
) -> float:
    weights = policy.weights
    analysis = context.analysis
    base = min(1.0, max(0.0, result.score))
    raw_rrf = _reciprocal_rank_fusion(result.source_ranks)
    evidence = build_ranking_evidence(result)
    raw_lexical = _lexical_signal(evidence, analysis)
    raw_phrase = _phrase_score(evidence, analysis)
    raw_proximity = _proximity_score(_token_sequence(evidence), analysis.tokens)
    raw_consensus = min(
        weights.consensus_cap,
        math.log1p(len(result.retrieval_sources)) * weights.consensus_scale,
    )
    raw_temporal = _temporal_salience(result.local_date, context.as_of_date)
    raw_temporal_query = temporal_window_match(result.local_date, context.temporal_window)
    raw_kind_prior = weights.document_kind_prior if result.source_kind == "document" else 0.0
    raw_graph_prior = weights.graph_prior if any("graph" in source for source in result.retrieval_sources) else 0.0
    raw_importance = importance_bonus(result.user_importance)
    contextual_salience = (
        result.entry_salience if result.entry_salience is not None else weights.contextual_salience_neutral
    )
    memory_prior = memory_type_salience(result.memory_type)
    social_intent = context.social_intent
    social = score_social_evidence(result, social_intent)

    lexical = raw_lexical if policy.lexical_evidence else 0.0
    phrase = raw_phrase if policy.lexical_evidence else 0.0
    proximity = raw_proximity if policy.lexical_evidence else 0.0
    rrf = raw_rrf if policy.rank_fusion else 0.0
    source_consensus = raw_consensus if policy.rank_fusion else 0.0
    temporal = raw_temporal if policy.structural_priors else 0.0
    temporal_query_bonus = weights.temporal_query * raw_temporal_query if policy.structural_priors else 0.0
    kind_prior = raw_kind_prior if policy.structural_priors else 0.0
    graph_prior = raw_graph_prior if policy.structural_priors else 0.0
    importance_query_gate = (
        1.0
        if social_intent.social_focus == 0.0
        else max(
            weights.importance_gate_floor,
            social.intent_coverage * max(weights.identity_match_floor, social.identity_match),
        )
    )
    explicit_importance = raw_importance * importance_query_gate if policy.salience_priors else 0.0
    contextual_delta = (
        (contextual_salience - weights.contextual_salience_neutral) * weights.contextual_salience
        if policy.salience_priors
        else 0.0
    )
    memory_delta = (
        (memory_prior - weights.memory_type_salience_neutral) * weights.memory_type_salience
        if policy.salience_priors
        else 0.0
    )
    social_bonus = (
        social_intent.social_focus * weights.social_utility * social.utility if policy.social_evidence else 0.0
    )
    social_penalty = (
        social_intent.social_focus * weights.factualization_penalty * social.factualization_risk
        if policy.social_evidence
        else 0.0
    )

    # Consensus between independent retrievers is more stable than comparing
    # their raw scores. RRF supplies that consensus while lexical evidence
    # protects exact names, phrases, and obscure details.
    blended = (
        (weights.base * base)
        + (weights.lexical * lexical)
        + (weights.phrase * phrase)
        + (weights.proximity * proximity)
        + (weights.reciprocal_rank * rrf)
    )
    relevance_score = min(
        1.0,
        max(0.0, max(base, blended) + source_consensus + temporal + kind_prior + graph_prior),
    )
    score = min(
        1.0,
        max(
            0.0,
            (weights.relevance * relevance_score)
            + temporal_query_bonus
            + explicit_importance
            + contextual_delta
            + memory_delta
            + social_bonus
            - social_penalty,
        ),
    )
    result.ranking_policy = policy.name
    result.ranking_signals = {
        "base": round(base, 4),
        "lexical": round(raw_lexical, 4),
        "phrase": round(raw_phrase, 4),
        "proximity": round(raw_proximity, 4),
        "rrf": round(raw_rrf, 4),
        "specificity": round(analysis.specificity, 4),
        "source_consensus": round(raw_consensus, 4),
        "temporal": round(raw_temporal, 4),
        "temporal_query_match": round(raw_temporal_query, 4),
        "temporal_query_bonus": round(temporal_query_bonus, 4),
        "user_importance": float(result.user_importance or 0),
        "importance_bonus": round(raw_importance, 4),
        "importance_query_gate": round(importance_query_gate, 4),
        "contextual_salience": round(contextual_salience, 4),
        "memory_type_salience": round(memory_prior, 4),
        "social_focus": round(social_intent.social_focus, 4),
        "social_utility": round(social.utility, 4),
        "social_intent_coverage": round(social.intent_coverage, 4),
        "social_identity_match": round(social.identity_match, 4),
        "attribution_quality": round(social.attribution_quality, 4),
        "scene_completeness": round(social.scene_completeness, 4),
        "narrative_salience": round(social.narrative_salience, 4),
        "epistemic_fit": round(social.epistemic_fit, 4),
        "factualization_risk": round(social.factualization_risk, 4),
        "social_bonus": round(social_bonus, 4),
        "social_penalty": round(social_penalty, 4),
        "relevance_before_importance": round(relevance_score, 4),
        "policy_lexical": float(policy.lexical_evidence),
        "policy_rank_fusion": float(policy.rank_fusion),
        "policy_structural_priors": float(policy.structural_priors),
        "policy_salience_priors": float(policy.salience_priors),
        "policy_social_evidence": float(policy.social_evidence),
        "policy_adaptive_diversity": float(policy.adaptive_diversity),
        "policy_narrative_coverage": float(policy.narrative_coverage),
        "final": round(score, 4),
    }
    return score


def _reciprocal_rank_fusion(source_ranks: dict[str, int], *, k: int = 60) -> float:
    if not source_ranks:
        return 0.0
    return sum(1.0 / (k + max(1, rank)) for rank in source_ranks.values())


def _temporal_salience(local_date: str, as_of_date: date) -> float:
    try:
        observed = date.fromisoformat(local_date)
    except (TypeError, ValueError):
        return 0.0
    age_days = max(0, (as_of_date - observed).days)
    return 0.015 * math.exp(-age_days / 180)


def _maximal_marginal_relevance(
    candidates: list[SearchResult],
    limit: int,
    context: _RankingContext,
    policy: RankingPolicy,
) -> list[SearchResult]:
    if len(candidates) <= limit:
        return candidates[:limit]

    all_candidates = candidates[:]
    selected: list[SearchResult] = []
    remaining = candidates[:]
    token_cache = {
        candidate.memory_id: _tokens(f"{candidate.text} {candidate.evidence_text}") for candidate in candidates
    }
    lambda_score = policy.diversity_lambda if policy.diversity_lambda is not None else 1.0
    requested_facets = context.requested_facets()
    covered_facets: set[str] = set()

    while remaining and len(selected) < limit:
        if not selected:
            first = remaining.pop(0)
            selected.append(first)
            covered_facets.update(context.facets(first))
            continue
        best_index = 0
        best_score = float("-inf")
        for index, candidate in enumerate(remaining):
            similarity = max(
                _jaccard(token_cache[candidate.memory_id], token_cache[chosen.memory_id]) for chosen in selected
            )
            mmr_score = (lambda_score * candidate.score) - ((1 - lambda_score) * similarity)
            if policy.narrative_coverage and requested_facets:
                marginal_facets = (context.facets(candidate) & requested_facets) - covered_facets
                # Explicitly requested scene facets deserve meaningful capacity.
                # The bonus is still bounded and applies only after candidate
                # generation has established baseline relevance.
                mmr_score += 0.24 * (len(marginal_facets) / len(requested_facets))
            if any(
                candidate.source_entry_id and candidate.source_entry_id == chosen.source_entry_id for chosen in selected
            ):
                mmr_score -= 0.025
            if mmr_score > best_score:
                best_index = index
                best_score = mmr_score
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        covered_facets.update(context.facets(chosen))

    if not policy.aspect_coverage:
        return _ensure_narrative_coverage(selected, all_candidates, context, policy)
    selected = _ensure_query_aspect_coverage(selected, all_candidates, token_cache, context, limit)
    return _ensure_narrative_coverage(selected, all_candidates, context, policy)


def _ensure_narrative_coverage(
    selected: list[SearchResult],
    candidates: list[SearchResult],
    context: _RankingContext,
    policy: RankingPolicy,
) -> list[SearchResult]:
    """Repair a result set that missed an explicitly requested scene facet.

    Replacements must improve facet coverage and stay within a bounded score
    distance. This prevents a metadata-rich but irrelevant candidate from
    displacing exact evidence while still reserving capacity for an answer's
    requested who/where/why structure.
    """
    if not policy.narrative_coverage or len(selected) < 2:
        return selected
    requested = context.requested_facets()
    if not requested:
        return selected

    selected_ids = {item.memory_id for item in selected}
    repairs = 0
    while repairs < min(3, len(selected) - 1):
        current_coverage = set().union(*(context.facets(item) for item in selected)) & requested
        missing = requested - current_coverage
        if not missing:
            break
        best: tuple[float, int, SearchResult] | None = None
        for candidate in candidates:
            if candidate.memory_id in selected_ids or not (context.facets(candidate) & missing):
                continue
            for index in range(1, len(selected)):
                trial = [*selected[:index], candidate, *selected[index + 1 :]]
                trial_coverage = set().union(*(context.facets(item) for item in trial)) & requested
                gain = len(trial_coverage) - len(current_coverage)
                score_loss = max(0.0, selected[index].score - candidate.score)
                objective = (0.16 * gain) - score_loss
                if gain > 0 and score_loss <= 0.18 and (best is None or objective > best[0]):
                    best = (objective, index, candidate)
        if best is None or best[0] <= 0:
            break
        _objective, replace_index, replacement = best
        selected_ids.discard(selected[replace_index].memory_id)
        selected[replace_index] = replacement
        selected_ids.add(replacement.memory_id)
        repairs += 1
    return selected


def _ensure_query_aspect_coverage(
    selected: list[SearchResult],
    candidates: list[SearchResult],
    token_cache: dict[str, set[str]],
    context: _RankingContext,
    limit: int,
) -> list[SearchResult]:
    """Reserve limited capacity for distinctive, otherwise-missed query terms."""
    analysis = context.analysis
    if len(selected) < 2 or len(analysis.tokens) < 2:
        return selected

    document_frequency = {
        token: sum(1 for candidate in candidates if token in token_cache[candidate.memory_id])
        for token in analysis.tokens
    }
    rare_threshold = max(3, math.ceil(len(candidates) * 0.20))
    selected_ids = {candidate.memory_id for candidate in selected}
    covered = set().union(*(token_cache[candidate.memory_id] for candidate in selected))
    missing_rare = sorted(
        (
            token
            for token in analysis.tokens
            if token not in covered and 0 < document_frequency.get(token, 0) <= rare_threshold
        ),
        key=lambda token: (
            document_frequency[token],
            token not in analysis.high_value_tokens,
            -len(token),
            token,
        ),
    )
    aspect_budget = min(3, max(1, limit // 4))
    protected_ids: set[str] = set()

    for token in missing_rare[:aspect_budget]:
        supporting = [
            candidate
            for candidate in candidates
            if candidate.memory_id not in selected_ids
            and token in token_cache[candidate.memory_id]
            and candidate.score >= 0.35
        ]
        if not supporting:
            continue
        replacement = max(supporting, key=lambda candidate: candidate.score)
        replaceable = [index for index in range(1, len(selected)) if selected[index].memory_id not in protected_ids]
        if not replaceable:
            break
        replace_index = min(replaceable, key=lambda index: selected[index].score)
        selected_ids.discard(selected[replace_index].memory_id)
        selected[replace_index] = replacement
        selected_ids.add(replacement.memory_id)
        protected_ids.add(replacement.memory_id)

    return selected


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
