"""Memory infrastructure audit checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import DocumentChunk, DocumentSource, Entity, IngestionJob, Memory, RawEntry, Relationship
from thoughtpins.memory.graph_backend import graph_backend_health
from thoughtpins.memory.ontology import relationship_allowed


@dataclass
class AuditIssue:
    severity: str
    code: str
    detail: str
    count: int = 0


@dataclass
class MemoryAuditReport:
    grade: str
    score: int
    issues: list[AuditIssue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    graph: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "grade": self.grade,
            "score": self.score,
            "issues": [asdict(issue) for issue in self.issues],
            "stats": self.stats,
            "graph": self.graph,
        }


def audit_memory_system(session: Session, *, user_id: str) -> MemoryAuditReport:
    issues: list[AuditIssue] = []
    stats = _stats(session, user_id)

    _duplicate_entities(session, user_id, issues)
    _invalid_relationships(session, user_id, issues)
    _document_quality(session, user_id, issues)
    _memory_index_shape(session, user_id, issues, stats)
    _job_health(session, user_id, issues)

    graph = graph_backend_health(session)
    if graph.get("status") not in {"ok", "configured"}:
        issues.append(
            AuditIssue(
                "info", "graph_aux_disabled", f"Graph backend: {graph.get('status')} {graph.get('detail', '')}".strip()
            )
        )

    score = 100
    for issue in issues:
        if issue.severity == "critical":
            score -= 20
        elif issue.severity == "high":
            score -= 12
        elif issue.severity == "medium":
            score -= 6
        elif issue.severity == "low":
            score -= 2
    score = max(0, min(100, score))
    return MemoryAuditReport(grade=_letter_grade(score), score=score, issues=issues, stats=stats, graph=graph)


def format_audit_report(report: MemoryAuditReport) -> str:
    lines = [
        "Memory Infra Audit",
        "==================",
        f"Grade: {report.grade} ({report.score}/100)",
        "",
        "Stats:",
    ]
    for key, value in report.stats.items():
        lines.append(f"  {key}: {value}")
    lines.extend(
        ["", "Graph:", f"  provider: {report.graph.get('provider')}", f"  status: {report.graph.get('status')}"]
    )
    detail = str(report.graph.get("detail") or "")
    if detail:
        lines.append(f"  detail: {detail[:160]}")
    if report.issues:
        lines.extend(["", "Issues:"])
        for issue in report.issues[:20]:
            count = f" ({issue.count})" if issue.count else ""
            lines.append(f"  {issue.severity.upper()} {issue.code}{count}: {issue.detail}")
    else:
        lines.extend(["", "Issues: none"])
    return "\n".join(lines)


def _stats(session: Session, user_id: str) -> dict[str, int]:
    models = {
        "raw_entries": RawEntry,
        "memories": Memory,
        "entities": Entity,
        "relationships": Relationship,
        "document_sources": DocumentSource,
        "document_chunks": DocumentChunk,
        "jobs": IngestionJob,
    }
    return {
        name: session.query(func.count(model.id)).filter(model.user_id == user_id).scalar() or 0
        for name, model in models.items()
    }


def _duplicate_entities(session: Session, user_id: str, issues: list[AuditIssue]) -> None:
    rows = (
        session.query(Entity.type, func.lower(Entity.canonical_name), func.count(Entity.id))
        .filter(Entity.user_id == user_id)
        .group_by(Entity.type, func.lower(Entity.canonical_name))
        .having(func.count(Entity.id) > 1)
        .all()
    )
    if rows:
        issues.append(AuditIssue("medium", "duplicate_entities", "Canonical entity names are duplicated.", len(rows)))


def _invalid_relationships(session: Session, user_id: str, issues: list[AuditIssue]) -> None:
    invalid = 0
    rels = session.query(Relationship).filter(Relationship.user_id == user_id).limit(5000).all()
    for rel in rels:
        if not rel.source_entity or not rel.target_entity:
            invalid += 1
            continue
        decision = relationship_allowed(rel.relation_type, rel.source_entity.type, rel.target_entity.type)
        if not decision.allowed:
            invalid += 1
    if invalid:
        issues.append(
            AuditIssue("high", "invalid_ontology_edges", "Relationships violate the typed memory ontology.", invalid)
        )


def _document_quality(session: Session, user_id: str, issues: list[AuditIssue]) -> None:
    metadata_only = (
        session.query(func.count(DocumentSource.id))
        .filter(
            DocumentSource.user_id == user_id,
            DocumentSource.rights_basis == "metadata_only",
        )
        .scalar()
        or 0
    )
    if metadata_only:
        issues.append(
            AuditIssue("low", "metadata_only_sources", "Some saved links need pasted/uploaded text.", metadata_only)
        )

    processed_without_chunks = (
        session.query(func.count(DocumentSource.id))
        .filter(
            DocumentSource.user_id == user_id,
            DocumentSource.status == "processed",
            ~DocumentSource.chunks.any(),
        )
        .scalar()
        or 0
    )
    if processed_without_chunks:
        issues.append(
            AuditIssue(
                "medium",
                "processed_sources_without_chunks",
                "Processed documents have no searchable chunks.",
                processed_without_chunks,
            )
        )


def _memory_index_shape(session: Session, user_id: str, issues: list[AuditIssue], stats: dict[str, int]) -> None:
    if stats["raw_entries"] and not stats["memories"]:
        issues.append(
            AuditIssue("high", "entries_without_memories", "Raw entries exist but no extracted memories are present.")
        )
    active_memories = (
        session.query(func.count(Memory.id))
        .filter(
            Memory.user_id == user_id,
            Memory.valid_to.is_(None),
        )
        .scalar()
        or 0
    )
    if stats["memories"] and active_memories == 0:
        issues.append(AuditIssue("high", "no_active_memories", "All memories are superseded or inactive."))


def _job_health(session: Session, user_id: str, issues: list[AuditIssue]) -> None:
    stale_after = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=config.INGESTION_STALE_AFTER_MINUTES
    )
    stale = (
        session.query(func.count(IngestionJob.id))
        .filter(
            IngestionJob.user_id == user_id,
            IngestionJob.status == "running",
            IngestionJob.started_at_utc < stale_after,
        )
        .scalar()
        or 0
    )
    if stale:
        issues.append(AuditIssue("high", "stale_running_jobs", "Ingestion jobs are stuck in running state.", stale))
    failed = (
        session.query(func.count(IngestionJob.id))
        .filter(
            IngestionJob.user_id == user_id,
            IngestionJob.status.in_(["failed", "dead_letter"]),
        )
        .scalar()
        or 0
    )
    if failed:
        issues.append(AuditIssue("medium", "failed_jobs", "Failed/dead-letter jobs need inspection.", failed))


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
