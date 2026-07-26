"""Turn ranked memories into a compact, provenance-aware response plan."""

from __future__ import annotations

from dataclasses import dataclass

from thoughtpins.memory.search_types import SearchResult
from thoughtpins.memory.social_relevance import SocialQueryIntent, analyze_social_query, score_social_evidence


@dataclass(frozen=True)
class PlannedEvidence:
    memory_id: str
    source_entry_id: str
    date: str
    text: str
    epistemic_status: str
    attributed_to: str
    people: tuple[str, ...]
    place: str
    provenance: str
    score: float


@dataclass(frozen=True)
class ResponseEvidencePlan:
    intent: SocialQueryIntent
    evidence: tuple[PlannedEvidence, ...]
    missing_facets: tuple[str, ...]

    def render(self) -> str:
        if not self.evidence:
            return ""
        requested = ", ".join(sorted(self.intent.facets)) or "general relevance"
        missing = ", ".join(self.missing_facets) or "none"
        lines = [
            f"Requested evidence facets: {requested}",
            f"Requested facets not present in selected evidence: {missing}",
            "Response rule: preserve the status and speaker of attributed, hearsay, inferred, disputed, or retracted claims. Do not restate them as verified facts.",
        ]
        for item in self.evidence:
            details = [
                f"id={item.memory_id[:12]}",
                f"date={item.date or 'undated'}",
                f"status={item.epistemic_status}",
            ]
            if item.attributed_to:
                details.append(f"speaker={item.attributed_to}")
            if item.people:
                details.append(f"people={', '.join(item.people[:6])}")
            if item.place:
                details.append(f"place={item.place}")
            if item.provenance:
                details.append(f"source={item.provenance[:100]}")
            lines.append(f"- {'; '.join(details)}\n  {item.text[:1200]}")
        return "\n".join(lines)


def build_response_evidence_plan(
    query: str,
    results: list[SearchResult],
    *,
    limit: int = 12,
) -> ResponseEvidencePlan:
    intent = analyze_social_query(query)
    evidence: list[PlannedEvidence] = []
    covered: set[str] = set()
    seen_sources: set[tuple[str, str]] = set()

    for result in results:
        features = score_social_evidence(result, intent)
        key = (result.source_entry_id or result.memory_id, result.text.strip().casefold())
        if key in seen_sources:
            continue
        seen_sources.add(key)
        covered.update(features.facets)
        evidence.append(
            PlannedEvidence(
                memory_id=result.memory_id,
                source_entry_id=result.source_entry_id,
                date=result.local_date,
                text=result.evidence_text or result.text,
                epistemic_status=features.epistemic_status,
                attributed_to=features.attributed_to,
                people=features.people,
                place=features.place,
                provenance=result.source_provenance,
                score=result.score,
            )
        )
        if len(evidence) >= limit:
            break

    return ResponseEvidencePlan(
        intent=intent,
        evidence=tuple(evidence),
        missing_facets=tuple(sorted(intent.facets - covered)),
    )
