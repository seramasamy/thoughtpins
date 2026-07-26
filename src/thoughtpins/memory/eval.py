"""Deterministic memory infrastructure evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from thoughtpins.db import DocumentChunk, DocumentSource, RawEntry, User
from thoughtpins.memory.audit import audit_memory_system
from thoughtpins.memory.context_package import build_memory_context_package
from thoughtpins.memory.evaluation_cases import MemoryEvalDefinition, memory_eval_definitions
from thoughtpins.memory.evaluation_fixture_store import (
    fixture_entity as _entity,
)
from thoughtpins.memory.evaluation_fixture_store import (
    fixture_memory as _memory,
)
from thoughtpins.memory.evaluation_fixture_store import (
    fixture_raw_entry as _raw,
)
from thoughtpins.memory.evaluation_fixture_store import (
    fixture_relationship as _relationship,
)
from thoughtpins.memory.evaluation_metrics import (
    AggregateRetrievalMetrics,
    RetrievalMetrics,
    aggregate_retrieval_metrics,
    evaluate_ranked_results,
)
from thoughtpins.memory.ranking import DEFAULT_RANKING_POLICY, RankingPolicy
from thoughtpins.memory.search import search
from thoughtpins.utils import hash_text


@dataclass
class EvalCase:
    name: str
    query: str
    expected_terms: list[str]
    passed: bool = False
    detail: str = ""
    retrieval_metrics: RetrievalMetrics | None = None


@dataclass
class RankingAblation:
    policy: str
    metrics: AggregateRetrievalMetrics
    delta_ndcg_at_k: float = 0.0
    delta_recall_at_k: float = 0.0


@dataclass
class MemoryInfraEvalResult:
    grade: str
    score: int
    cases: list[EvalCase] = field(default_factory=list)
    audit_grade: str = ""
    audit_score: int = 0
    retrieval_metrics: AggregateRetrievalMetrics | None = None
    ranking_ablations: list[RankingAblation] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "grade": self.grade,
            "score": self.score,
            "audit_grade": self.audit_grade,
            "audit_score": self.audit_score,
            "retrieval_metrics": self.retrieval_metrics.as_dict() if self.retrieval_metrics else None,
            "ranking_ablations": [
                {
                    "policy": ablation.policy,
                    "metrics": ablation.metrics.as_dict(),
                    "delta_ndcg_at_k": ablation.delta_ndcg_at_k,
                    "delta_recall_at_k": ablation.delta_recall_at_k,
                }
                for ablation in self.ranking_ablations
            ],
            "cases": [asdict(case) for case in self.cases],
        }


def seed_memory_infra_fixture(session: Session, *, user_id: str | None = None) -> str:
    user = User(id=user_id or "eval_memory_user", email="eval-memory@example.local", display_name="Memory Eval")
    session.merge(user)
    session.flush()

    alice = _entity(session, user.id, "Alice", "person")
    atlas = _entity(session, user.id, "Project Atlas", "project")
    postgres = _entity(session, user.id, "PostgreSQL", "technology")
    priya = _entity(session, user.id, "Priya", "person")
    cafe = _entity(session, user.id, "Marlow Coffee", "place")
    maya = _entity(session, user.id, "Maya", "person")
    lumen = _entity(session, user.id, "Lumen Bar", "place")
    date_night = _entity(session, user.id, "Koyo date night", "event")
    koyo = _entity(session, user.id, "Koyo Ramen", "place")
    willow = _entity(session, user.id, "Willow Park", "place")
    daniel = _entity(session, user.id, "Daniel", "person")
    goodwin = _entity(session, user.id, "Goodwin Hall", "place")
    terraloop = _entity(session, user.id, "TerraLoop", "organization")
    compliance_tooling = _entity(session, user.id, "compliance tooling", "topic")
    northstar = _entity(session, user.id, "Northstar Memory", "project")
    recall_diagnostics = _entity(session, user.id, "recall diagnostics", "technology")
    prayer = _entity(session, user.id, "listening prayer", "concept")
    nora = _entity(session, user.id, "Nora", "person")
    eli = _entity(session, user.id, "Eli", "person")
    halcyon = _entity(session, user.id, "Halcyon House", "place")
    ava = _entity(session, user.id, "Ava", "person")
    sam = _entity(session, user.id, "Sam", "person")
    school_library = _entity(session, user.id, "Westbridge Library", "place")
    celia = _entity(session, user.id, "Celia", "person")
    north_gallery = _entity(session, user.id, "North Gallery", "organization")

    raw1 = _raw(
        session, user.id, "At Marlow Coffee, Priya said the backup restore path matters more than animation polish."
    )
    _memory(
        session, user.id, raw1, "Priya said the backup restore path matters more than animation polish.", subject=priya
    )
    _relationship(session, user.id, raw1, priya, cafe, "met_at")

    raw2 = _raw(session, user.id, "Alice manages Project Atlas. Project Atlas runs on PostgreSQL.")
    _memory(session, user.id, raw2, "Alice manages Project Atlas.", subject=alice, obj=atlas)
    _memory(session, user.id, raw2, "Project Atlas uses PostgreSQL.", subject=atlas, obj=postgres)
    _relationship(session, user.id, raw2, alice, atlas, "works_on")
    _relationship(session, user.id, raw2, atlas, postgres, "uses_technology")

    raw3 = _raw(session, user.id, "The PostgreSQL cluster went down Tuesday and affected Project Atlas.")
    _memory(
        session,
        user.id,
        raw3,
        "The PostgreSQL cluster outage Tuesday affected Project Atlas.",
        subject=atlas,
        obj=postgres,
    )

    raw_bar = _raw(
        session,
        user.id,
        "Quick bar note: at Lumen Bar, Maya said the rye sour works because bitters offset the orange peel.",
    )
    _memory(
        session,
        user.id,
        raw_bar,
        "At Lumen Bar, Maya said the rye sour works because bitters offset the orange peel.",
        subject=maya,
        obj=lumen,
    )
    _relationship(session, user.id, raw_bar, maya, lumen, "met_at")

    raw_rumor = _raw(
        session,
        user.id,
        "At Halcyon House, Nora said she had heard Eli might leave the paper after the winter gala.",
    )
    _memory(
        session,
        user.id,
        raw_rumor,
        "Nora said she had heard Eli might leave the paper after the winter gala.",
        memory_type="quote",
        subject=nora,
        obj=eli,
        confidence="hearsay_from_person",
        predicate="said",
        structured_json={
            "attributed_to": "Nora",
            "people_involved": ["Nora", "Eli"],
            "place": "Halcyon House",
            "epistemic_status": "hearsay_from_person",
            "claim_status": "disputed",
            "social_stakes": "high",
            "open_loop": True,
        },
    )
    _relationship(session, user.id, raw_rumor, nora, halcyon, "met_at")
    raw_retraction = _raw(
        session,
        user.id,
        "Two days later Nora retracted the story after Eli denied planning to leave the paper.",
    )
    _memory(
        session,
        user.id,
        raw_retraction,
        "Nora retracted the story; Eli denied planning to leave the paper.",
        memory_type="relationship_update",
        subject=nora,
        obj=eli,
        confidence="user_reported",
        predicate="retracted",
        structured_json={
            "attributed_to": "Nora",
            "people_involved": ["Nora", "Eli"],
            "epistemic_status": "attributed_statement",
            "claim_status": "retracted",
            "consequence": "Eli's denial closed the rumor thread.",
            "social_stakes": "high",
            "open_loop": False,
        },
    )

    raw_school = _raw(
        session,
        user.id,
        "At Westbridge Library, Ava said Sam skipped rehearsal because an older student mocked his audition draft.",
    )
    _memory(
        session,
        user.id,
        raw_school,
        "Ava said Sam skipped rehearsal because an older student mocked his audition draft.",
        memory_type="social_dynamic",
        subject=ava,
        obj=sam,
        confidence="user_reported",
        predicate="explained",
        structured_json={
            "attributed_to": "Ava",
            "people_involved": ["Ava", "Sam"],
            "place": "Westbridge Library",
            "epistemic_status": "attributed_statement",
            "claim_status": "active",
            "motivation": "Sam was mocked about his audition draft.",
            "consequence": "Sam skipped rehearsal.",
            "social_stakes": "medium",
        },
    )
    _relationship(session, user.id, raw_school, ava, school_library, "met_at")

    raw_creative = _raw(
        session,
        user.id,
        "In Celia's studio, she said North Gallery wanted a smaller series because the blue canvases held together best.",
    )
    _memory(
        session,
        user.id,
        raw_creative,
        "Celia said North Gallery wanted a smaller series because the blue canvases held together best.",
        memory_type="decision",
        subject=celia,
        obj=north_gallery,
        confidence="user_reported",
        predicate="explained",
        structured_json={
            "attributed_to": "Celia",
            "people_involved": ["Celia"],
            "place": "Celia's studio",
            "epistemic_status": "attributed_statement",
            "claim_status": "active",
            "motivation": "The blue canvases formed the strongest coherent set.",
            "consequence": "The proposed exhibition series became smaller.",
            "social_stakes": "medium",
        },
    )

    raw_date = _raw(
        session,
        user.id,
        "Date night note: at Koyo Ramen we talked about renting near Willow Park and made a no-phones-at-dinner rule.",
    )
    _memory(
        session,
        user.id,
        raw_date,
        "At Koyo Ramen, date night included talking about renting near Willow Park and a no-phones-at-dinner rule.",
        subject=koyo,
        obj=willow,
    )
    _relationship(session, user.id, raw_date, date_night, koyo, "located_at")

    raw_networking = _raw(
        session,
        user.id,
        "Networking event note: met Daniel at Goodwin Hall; he runs partnerships at TerraLoop and cares about compliance tooling.",
    )
    _memory(
        session,
        user.id,
        raw_networking,
        "Daniel runs partnerships at TerraLoop and cares about compliance tooling.",
        subject=daniel,
        obj=terraloop,
    )
    _memory(
        session,
        user.id,
        raw_networking,
        "Daniel discussed compliance tooling at Goodwin Hall.",
        subject=daniel,
        obj=compliance_tooling,
    )
    _relationship(session, user.id, raw_networking, daniel, goodwin, "met_at")
    _relationship(session, user.id, raw_networking, daniel, terraloop, "works_with")
    _relationship(session, user.id, raw_networking, daniel, compliance_tooling, "discussed")

    raw_recipe = _raw(
        session,
        user.id,
        "Recipe note: turmeric lentil stew needs chickpeas, tomato, cumin, garlic, lemon, parsley, and a spoon of yogurt at the end.",
    )
    _memory(
        session,
        user.id,
        raw_recipe,
        "Turmeric lentil stew recipe: chickpeas, tomato, cumin, garlic, lemon, parsley, and yogurt at the end.",
    )

    raw_business = _raw(
        session,
        user.id,
        "Business idea: Northstar Memory should stay local-first but include explicit recall diagnostics before any social features.",
    )
    _memory(
        session,
        user.id,
        raw_business,
        "Northstar Memory should stay local-first and prioritize explicit recall diagnostics before social features.",
        subject=northstar,
        obj=recall_diagnostics,
    )
    _relationship(session, user.id, raw_business, northstar, recall_diagnostics, "uses_technology")

    raw_spiritual = _raw(
        session,
        user.id,
        "Spiritual thought: prayer felt less like asking and more like listening tonight; attention is a budget, not a mood.",
    )
    _memory(
        session,
        user.id,
        raw_spiritual,
        "Prayer felt less like asking and more like listening; attention is a budget, not a mood.",
        subject=prayer,
    )

    raw4 = _raw(session, user.id, "The old paper mentioned the violet keystone detail as the decisive recall test.")
    doc = DocumentSource(
        user_id=user.id,
        raw_entry_id=raw4.id,
        source_type="article",
        title="Old Recall Paper",
        source_url="https://example.com/old-recall-paper",
        canonical_url="https://example.com/old-recall-paper",
        source_domain="example.com",
        access_method="user_paste",
        rights_basis="user_provided",
        fetch_status="processed",
        paywall_detected=False,
        retrieval_quality_score=0.9,
        content_hash=hash_text("old recall paper"),
        raw_text="The old paper mentioned the violet keystone detail as the decisive recall test.",
        summary="The paper names the violet keystone detail as a recall test.",
        status="processed",
        local_date=raw4.local_date,
    )
    session.add(doc)
    session.flush()
    session.add(
        DocumentChunk(
            user_id=user.id,
            document_id=doc.id,
            chunk_index=0,
            text=doc.raw_text,
            char_start=0,
            char_end=len(doc.raw_text),
            token_count=18,
        )
    )
    _memory(
        session,
        user.id,
        raw4,
        "From source 'Old Recall Paper' chunk 1: The old paper mentioned the violet keystone detail as the decisive recall test.",
        memory_type="source_excerpt",
        structured_json={
            "source_kind": "document",
            "document_id": doc.id,
            "title": doc.title,
            "source_url": doc.source_url,
            "evidence_text": doc.raw_text,
        },
    )

    raw_book = _raw(
        session,
        user.id,
        "The book note said Chapter Seven of the Sable Notebook series used the amber compass ritual to remember the river city twins.",
    )
    book = DocumentSource(
        user_id=user.id,
        raw_entry_id=raw_book.id,
        source_type="book",
        title="Sable Notebook - Chapter Seven",
        source_url="",
        canonical_url="",
        source_domain="",
        access_method="user_paste",
        rights_basis="user_provided",
        fetch_status="processed",
        paywall_detected=False,
        retrieval_quality_score=0.95,
        content_hash=hash_text("sable notebook chapter seven"),
        raw_text=(
            "Chapter Seven of the Sable Notebook series used the amber compass ritual to remember the river city twins."
        ),
        summary="Chapter Seven links the amber compass ritual to the river city twins.",
        status="processed",
        local_date=raw_book.local_date,
    )
    session.add(book)
    session.flush()
    session.add(
        DocumentChunk(
            user_id=user.id,
            document_id=book.id,
            chunk_index=0,
            text=book.raw_text,
            char_start=0,
            char_end=len(book.raw_text),
            token_count=19,
        )
    )
    _memory(
        session,
        user.id,
        raw_book,
        "From source 'Sable Notebook - Chapter Seven' chunk 1: the amber compass ritual helps remember the river city twins.",
        memory_type="source_excerpt",
        structured_json={
            "source_kind": "document",
            "document_id": book.id,
            "title": book.title,
            "source_url": book.source_url,
            "evidence_text": book.raw_text,
        },
    )

    raw_scarlet = _raw(
        session,
        user.id,
        "Public-domain novel note: in A Study in Scarlet, the wall clue was the word RACHE.",
    )
    scarlet = DocumentSource(
        user_id=user.id,
        raw_entry_id=raw_scarlet.id,
        source_type="book",
        title="A Study in Scarlet",
        source_url="https://www.gutenberg.org/ebooks/244",
        canonical_url="https://www.gutenberg.org/ebooks/244",
        source_domain="gutenberg.org",
        access_method="public_domain_fixture",
        rights_basis="public_domain",
        fetch_status="processed",
        paywall_detected=False,
        retrieval_quality_score=0.95,
        content_hash=hash_text("a study in scarlet rache"),
        raw_text="A Study in Scarlet fixture: the wall clue was the word RACHE.",
        summary="Public-domain Sherlock Holmes note: the wall clue was RACHE.",
        status="processed",
        local_date=raw_scarlet.local_date,
    )
    session.add(scarlet)
    session.flush()
    session.add(
        DocumentChunk(
            user_id=user.id,
            document_id=scarlet.id,
            chunk_index=0,
            text=scarlet.raw_text,
            char_start=0,
            char_end=len(scarlet.raw_text),
            token_count=14,
        )
    )
    _memory(
        session,
        user.id,
        raw_scarlet,
        "From source 'A Study in Scarlet' chunk 1: the wall clue was the word RACHE.",
        memory_type="source_excerpt",
        structured_json={
            "source_kind": "document",
            "document_id": scarlet.id,
            "title": scarlet.title,
            "source_url": scarlet.source_url,
            "evidence_text": scarlet.raw_text,
        },
    )

    raw_meditations = _raw(
        session,
        user.id,
        "Public-domain philosophy note: Marcus Aurelius warns not to live as if there were ten thousand years.",
    )
    meditations = DocumentSource(
        user_id=user.id,
        raw_entry_id=raw_meditations.id,
        source_type="book",
        title="Meditations",
        source_url="https://www.gutenberg.org/ebooks/2680",
        canonical_url="https://www.gutenberg.org/ebooks/2680",
        source_domain="gutenberg.org",
        access_method="public_domain_fixture",
        rights_basis="public_domain",
        fetch_status="processed",
        paywall_detected=False,
        retrieval_quality_score=0.95,
        content_hash=hash_text("meditations ten thousand years"),
        raw_text="Meditations fixture: do not live as if there were ten thousand years.",
        summary="Public-domain Stoic note: do not live as if there were ten thousand years.",
        status="processed",
        local_date=raw_meditations.local_date,
    )
    session.add(meditations)
    session.flush()
    session.add(
        DocumentChunk(
            user_id=user.id,
            document_id=meditations.id,
            chunk_index=0,
            text=meditations.raw_text,
            char_start=0,
            char_end=len(meditations.raw_text),
            token_count=14,
        )
    )
    _memory(
        session,
        user.id,
        raw_meditations,
        "From source 'Meditations' chunk 1: do not live as if there were ten thousand years.",
        memory_type="source_excerpt",
        structured_json={
            "source_kind": "document",
            "document_id": meditations.id,
            "title": meditations.title,
            "source_url": meditations.source_url,
            "evidence_text": meditations.raw_text,
        },
    )
    session.commit()
    return user.id


def run_memory_infra_eval(session: Session, *, user_id: str) -> MemoryInfraEvalResult:
    definitions = memory_eval_definitions()
    cases: list[EvalCase] = []
    entry_rows = [
        (str(entry_id), str(raw_text))
        for entry_id, raw_text in session.query(RawEntry.id, RawEntry.raw_text)
        .filter(RawEntry.user_id == user_id)
        .all()
    ]
    policies = _ranking_policies()
    policy_metrics: dict[str, list[RetrievalMetrics]] = {policy.name: [] for policy in policies}

    for definition in definitions:
        case = EvalCase(definition.name, definition.query, list(definition.expected_terms))
        cases.append(case)
        relevance = _resolve_relevance(definition, entry_rows)
        if definition.use_context_package:
            text = build_memory_context_package(
                case.query,
                session,
                user_id=user_id,
                include_private=False,
                include_vault=False,
                max_chars=80_000,
            )
        else:
            results = search(
                case.query,
                session=session,
                user_id=user_id,
                include_private=False,
                limit=10,
                ranking_policy=DEFAULT_RANKING_POLICY,
            )
            case.retrieval_metrics = evaluate_ranked_results(
                results,
                relevance_by_source_entry=relevance,
                expected_terms=definition.expected_terms,
                cutoff=10,
            )
            policy_metrics[DEFAULT_RANKING_POLICY.name].append(case.retrieval_metrics)
            for policy in policies[1:]:
                ablated = search(
                    case.query,
                    session=session,
                    user_id=user_id,
                    include_private=False,
                    limit=10,
                    ranking_policy=policy,
                )
                policy_metrics[policy.name].append(
                    evaluate_ranked_results(
                        ablated,
                        relevance_by_source_entry=relevance,
                        expected_terms=definition.expected_terms,
                        cutoff=10,
                    )
                )
            text = "\n".join(f"{result.text}\n{result.evidence_text}" for result in results)
        lowered = text.lower()
        missing = [term for term in case.expected_terms if term.lower() not in lowered]
        case.passed = not missing
        case.detail = "ok" if case.passed else f"missing: {', '.join(missing)}"

    audit = audit_memory_system(session, user_id=user_id)
    retrieval = aggregate_retrieval_metrics(policy_metrics[DEFAULT_RANKING_POLICY.name])
    ablations = _summarize_ablations(policies, policy_metrics, retrieval)
    pass_rate = sum(1 for case in cases if case.passed) / max(1, len(cases))
    score = round(
        (pass_rate * 30)
        + ((audit.score / 100) * 15)
        + (retrieval.mean_ndcg_at_k * 20)
        + (retrieval.mean_recall_at_k * 15)
        + (retrieval.mean_reciprocal_rank * 10)
        + (retrieval.mean_evidence_coverage * 10)
    )
    return MemoryInfraEvalResult(
        grade=_letter_grade(score),
        score=score,
        cases=cases,
        audit_grade=audit.grade,
        audit_score=audit.score,
        retrieval_metrics=retrieval,
        ranking_ablations=ablations,
    )


def _ranking_policies() -> tuple[RankingPolicy, ...]:
    return (
        DEFAULT_RANKING_POLICY,
        RankingPolicy(name="without-lexical-evidence", lexical_evidence=False),
        RankingPolicy(name="without-rank-fusion", rank_fusion=False),
        RankingPolicy(name="without-structural-priors", structural_priors=False),
        RankingPolicy(name="without-salience-priors", salience_priors=False),
        RankingPolicy(name="without-social-evidence", social_evidence=False, narrative_coverage=False),
        RankingPolicy(name="without-diversity", diversity_lambda=None, aspect_coverage=False, narrative_coverage=False),
    )


def _resolve_relevance(
    definition: MemoryEvalDefinition,
    entry_rows: list[tuple[str, str]],
) -> dict[str, float]:
    relevant: dict[str, float] = {}
    for marker in definition.relevance_markers:
        matches = [entry_id for entry_id, text in entry_rows if marker.lower() in text.lower()]
        if not matches:
            raise RuntimeError(f"memory eval relevance marker matched no fixture entry: {marker}")
        relevant.update({entry_id: 1.0 for entry_id in matches})
    return relevant


def _summarize_ablations(
    policies: tuple[RankingPolicy, ...],
    policy_metrics: dict[str, list[RetrievalMetrics]],
    baseline: AggregateRetrievalMetrics,
) -> list[RankingAblation]:
    summaries: list[RankingAblation] = []
    for policy in policies:
        metrics = aggregate_retrieval_metrics(policy_metrics[policy.name])
        summaries.append(
            RankingAblation(
                policy=policy.name,
                metrics=metrics,
                delta_ndcg_at_k=round(metrics.mean_ndcg_at_k - baseline.mean_ndcg_at_k, 6),
                delta_recall_at_k=round(metrics.mean_recall_at_k - baseline.mean_recall_at_k, 6),
            )
        )
    return summaries


def _letter_grade(score: int) -> str:
    if score >= 97:
        return "A+"
    if score >= 93:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 87:
        return "B+"
    if score >= 83:
        return "B"
    if score >= 80:
        return "B-"
    if score >= 70:
        return "C"
    return "D"
