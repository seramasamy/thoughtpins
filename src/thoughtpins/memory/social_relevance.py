"""Query-conditioned social and episodic relevance signals.

The vector, lexical, and graph retrievers answer "what might match?".  This
module answers the narrower question "which matching evidence helps a person
understand the scene?".  It is deliberately deterministic and side-effect
free so ranking decisions can be replayed, ablated, and audited.

Epistemic status is descriptive, not a probability of truth.  In particular,
hearsay may be exactly what a user is trying to remember, but it must retain an
attribution before it can be included in a response plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any, Mapping

from thoughtpins.memory.search_types import SearchResult

FACET_PEOPLE = "people"
FACET_STATEMENT = "statement"
FACET_PLACE = "place"
FACET_TIME = "time"
FACET_CAUSE = "cause"
FACET_OUTCOME = "outcome"
FACET_RELATIONSHIP = "relationship"
FACET_UNCERTAINTY = "uncertainty"
FACET_OPEN_LOOP = "open_loop"

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_FACET_CUES: dict[str, frozenset[str]] = {
    FACET_PEOPLE: frozenset({"who", "person", "people", "someone", "involved", "attended"}),
    FACET_STATEMENT: frozenset(
        {"say", "said", "says", "tell", "told", "mention", "mentioned", "claim", "claimed", "quote", "heard"}
    ),
    FACET_PLACE: frozenset({"where", "place", "location", "venue", "restaurant", "bar", "cafe", "met"}),
    FACET_TIME: frozenset({"when", "date", "before", "after", "during", "timeline", "first", "last"}),
    FACET_CAUSE: frozenset({"why", "reason", "because", "motive", "motivated", "purpose"}),
    FACET_OUTCOME: frozenset({"happened", "result", "outcome", "consequence", "afterward", "next"}),
    FACET_RELATIONSHIP: frozenset(
        {"relationship", "friend", "friends", "dating", "knows", "coworker", "conflict", "tension", "dynamic"}
    ),
    FACET_UNCERTAINTY: frozenset(
        {"rumor", "rumour", "gossip", "allegedly", "apparently", "heard", "true", "confirmed", "uncertain", "disputed"}
    ),
    FACET_OPEN_LOOP: frozenset({"unresolved", "pending", "followup", "follow-up", "open", "waiting"}),
}

_DIRECT_STATUSES = frozenset({"observed_by_user", "user_reported", "direct_observation", "self_report"})
_ATTRIBUTED_STATUSES = frozenset({"attributed_statement", "hearsay_from_person", "reported_by_person"})
_UNCERTAIN_STATUSES = frozenset({"hearsay_from_person", "inferred_by_model", "disputed", "retracted", "uncertain"})


@dataclass(frozen=True)
class SocialQueryIntent:
    """Social facets explicitly requested by a query."""

    facets: frozenset[str]
    query_tokens: frozenset[str]
    requested_person: str
    social_focus: float
    asks_about_uncertainty: bool


@dataclass(frozen=True)
class SocialEvidenceFeatures:
    """Bounded candidate features consumed by ranking and response planning."""

    facets: frozenset[str]
    people: tuple[str, ...]
    attributed_to: str
    place: str
    epistemic_status: str
    intent_coverage: float
    identity_match: float
    attribution_quality: float
    scene_completeness: float
    narrative_salience: float
    epistemic_fit: float
    factualization_risk: float

    @property
    def utility(self) -> float:
        value = (
            (0.24 * self.intent_coverage)
            + (0.30 * self.identity_match)
            + (0.14 * self.attribution_quality)
            + (0.12 * self.scene_completeness)
            + (0.10 * self.narrative_salience)
            + (0.10 * self.epistemic_fit)
            - (0.30 * self.factualization_risk)
        )
        return _clamp(value)


def analyze_social_query(query: str) -> SocialQueryIntent:
    tokens = _tokens(query)
    facets = {facet for facet, cues in _FACET_CUES.items() if tokens & cues}
    lowered = query.lower()
    if "who said" in lowered or "what did" in lowered:
        facets.update({FACET_PEOPLE, FACET_STATEMENT})
    if "where did" in lowered or "where was" in lowered:
        facets.add(FACET_PLACE)
    if "why did" in lowered or "why was" in lowered:
        facets.add(FACET_CAUSE)
    if "what happened" in lowered:
        facets.update({FACET_OUTCOME, FACET_TIME})

    weighted = sum(1.0 if facet in {FACET_STATEMENT, FACET_CAUSE, FACET_RELATIONSHIP} else 0.7 for facet in facets)
    social_focus = _clamp(weighted / 3.0)
    return SocialQueryIntent(
        facets=frozenset(facets),
        query_tokens=frozenset(tokens),
        requested_person=_requested_person(query),
        social_focus=social_focus,
        asks_about_uncertainty=FACET_UNCERTAINTY in facets,
    )


def score_social_evidence(result: SearchResult, intent: SocialQueryIntent) -> SocialEvidenceFeatures:
    metadata = result.evidence_metadata or {}
    status = _epistemic_status(result.confidence, metadata)
    attributed_to = _first_text(metadata, "attributed_to", "speaker", "source_person", "reported_by")
    people = _people(result, metadata, attributed_to)
    place = _first_text(metadata, "place", "location", "venue")
    facets = _candidate_facets(result, metadata, people=people, place=place, status=status, attributed_to=attributed_to)

    if intent.facets:
        coverage = len(intent.facets & facets) / len(intent.facets)
    else:
        coverage = 0.0

    is_statement = FACET_STATEMENT in facets
    attribution_quality = 1.0 if attributed_to else (0.62 if is_statement and people else 0.0)
    scene_facets = facets & {
        FACET_PEOPLE,
        FACET_STATEMENT,
        FACET_PLACE,
        FACET_TIME,
        FACET_CAUSE,
        FACET_OUTCOME,
        FACET_RELATIONSHIP,
    }
    scene_completeness = len(scene_facets) / 7.0
    narrative_salience = _narrative_salience(result, metadata, facets, people)
    identity_match = _identity_match(people, intent.query_tokens, intent.requested_person)
    epistemic_fit = _epistemic_fit(status, intent)
    factualization_risk = 1.0 if status in _UNCERTAIN_STATUSES and not attributed_to else 0.0

    return SocialEvidenceFeatures(
        facets=frozenset(facets),
        people=tuple(people),
        attributed_to=attributed_to,
        place=place,
        epistemic_status=status,
        intent_coverage=_clamp(coverage),
        identity_match=_clamp(identity_match),
        attribution_quality=_clamp(attribution_quality),
        scene_completeness=_clamp(scene_completeness),
        narrative_salience=_clamp(narrative_salience),
        epistemic_fit=_clamp(epistemic_fit),
        factualization_risk=_clamp(factualization_risk),
    )


@cache
def _no_query_intent() -> SocialQueryIntent:
    """The intent of asking nothing, which is what facet extraction scores against.

    Facets describe what a candidate *contains*, so the query side is empty and
    the answer is a constant — but re-parsing that empty query cost more than
    the facet extraction it set up. Computed on first use rather than at import,
    because the parser it calls is defined further down this module.
    """
    return analyze_social_query("")


def candidate_facets(result: SearchResult) -> frozenset[str]:
    """Which social facets this candidate carries, independent of any query."""
    return score_social_evidence(result, _no_query_intent()).facets


def _candidate_facets(
    result: SearchResult,
    metadata: Mapping[str, Any],
    *,
    people: list[str],
    place: str,
    status: str,
    attributed_to: str,
) -> set[str]:
    facets: set[str] = set()
    text = " ".join((result.text, result.evidence_text, result.predicate)).lower()
    memory_type = result.memory_type.lower()

    if people:
        facets.add(FACET_PEOPLE)
    if attributed_to or memory_type == "quote" or _first_text(metadata, "quote", "statement"):
        facets.add(FACET_STATEMENT)
    if place or any(term in result.predicate.lower() for term in ("at", "located", "visited")):
        facets.add(FACET_PLACE)
    if result.local_date or _first_text(metadata, "relative_date", "temporal_expression"):
        facets.add(FACET_TIME)
    if _first_text(metadata, "motivation", "reason", "cause", "purpose") or " because " in f" {text} ":
        facets.add(FACET_CAUSE)
    if _first_text(metadata, "consequence", "outcome", "result"):
        facets.add(FACET_OUTCOME)
    if memory_type in {"relationship", "relationship_update", "social_dynamic"} or result.predicate:
        facets.add(FACET_RELATIONSHIP)
    if status in _UNCERTAIN_STATUSES:
        facets.add(FACET_UNCERTAINTY)
    if _as_bool(metadata.get("open_loop")) or memory_type in {"commitment", "future_plan"}:
        facets.add(FACET_OPEN_LOOP)
    return facets


def _people(result: SearchResult, metadata: Mapping[str, Any], attributed_to: str) -> list[str]:
    values: list[str] = list(result.entity_names)
    for key in ("people_involved", "participants"):
        values.extend(_text_list(metadata.get(key)))
    for key in ("subject", "object", "speaker", "attributed_to", "reported_by"):
        value = _text(metadata.get(key))
        if value:
            values.append(value)
    if attributed_to:
        values.append(attributed_to)
    return _dedupe(values)


def _narrative_salience(
    result: SearchResult,
    metadata: Mapping[str, Any],
    facets: set[str],
    people: list[str],
) -> float:
    stakes = str(metadata.get("social_stakes") or metadata.get("stakes") or "").strip().lower()
    stakes_score = {"high": 1.0, "medium": 0.65, "low": 0.25}.get(stakes, 0.0)
    durable_type = (
        1.0
        if result.memory_type.lower()
        in {
            "decision",
            "relationship_update",
            "social_dynamic",
            "quote",
            "event",
            "commitment",
        }
        else 0.35
    )
    social_shape = _clamp((len(people) + len(facets & {FACET_STATEMENT, FACET_CAUSE, FACET_OUTCOME})) / 5.0)
    return (0.38 * stakes_score) + (0.34 * durable_type) + (0.28 * social_shape)


def _identity_match(people: list[str], query_tokens: frozenset[str], requested_person: str) -> float:
    """Measure whether a candidate's person identity was named in the query."""
    if not people or not query_tokens:
        return 0.0
    requested_tokens = _tokens(requested_person)
    best = 0.0
    for person in people:
        person_tokens = _tokens(person)
        if not person_tokens:
            continue
        if requested_tokens:
            if person.casefold().strip() == requested_person.casefold().strip():
                coverage = 1.0
            else:
                coverage = 0.5 * len(person_tokens & requested_tokens) / len(person_tokens | requested_tokens)
        else:
            coverage = 0.5 * len(person_tokens & query_tokens) / len(person_tokens)
        best = max(best, coverage)
    return best


def _requested_person(query: str) -> str:
    """Extract a named speaker slot without treating source titles as people."""
    compact = re.sub(r"\s+", " ", query or "").strip()
    patterns = (
        r"\bwhat\s+(?:rumou?r|gossip|claim|story)\s+did\s+(.{1,80}?)\s+"
        r"(?:share|tell|mention|repeat|say)\b",
        r"\bwhat\s+did\s+(.{1,80}?)\s+(?:say|tell|mention|claim|share|write)\b",
        r"\bwhat\s+has\s+(.{1,80}?)\s+(?:said|told|mentioned|claimed|shared|written)\b",
        r"\b(?:quote|statement)\s+(?:from|by)\s+(.{1,80}?)(?:[?.!,]|$)",
    )
    for pattern in patterns:
        if match := re.search(pattern, compact, flags=re.IGNORECASE):
            return match.group(1).strip(" \"'.,?!")
    return ""


def _epistemic_fit(status: str, intent: SocialQueryIntent) -> float:
    if intent.asks_about_uncertainty:
        return 1.0 if status in _UNCERTAIN_STATUSES or status in _ATTRIBUTED_STATUSES else 0.45
    if status in _DIRECT_STATUSES:
        return 1.0
    if status in _ATTRIBUTED_STATUSES:
        return 0.78
    if status == "inferred_by_model":
        return 0.42
    if status == "retracted":
        return 0.12
    return 0.35


def _epistemic_status(confidence: str, metadata: Mapping[str, Any]) -> str:
    explicit = _first_text(metadata, "epistemic_status", "claim_status").lower()
    value = explicit or (confidence or "observed_by_user").strip().lower()
    return value if value else "observed_by_user"


def _first_text(values: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(values.get(key))
        if value:
            return value
    return ""


def _text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()


def _text_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [text for item in value if (text := _text(item))]
    text = _text(value)
    return [text] if text else []


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "open"}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
