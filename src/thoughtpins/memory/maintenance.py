"""Offline memory maintenance tasks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from thoughtpins.db import Entity, Memory
from thoughtpins.jobs import recover_pending_jobs
from thoughtpins.memory.reindex import reindex_vectors
from thoughtpins.store import get_session


@dataclass
class MaintenanceReport:
    recovered_jobs: int = 0
    duplicate_entity_groups: list[list[str]] = field(default_factory=list)
    superseded_memories: int = 0
    reindex: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_memory_maintenance(
    *,
    session: Session | None = None,
    user_id: str | None = None,
    reindex: bool = False,
    include_private: bool = True,
) -> MaintenanceReport:
    owned_session = session is None
    if session is None:
        session = get_session()
    report = MaintenanceReport()
    try:
        report.recovered_jobs = recover_pending_jobs()
        report.duplicate_entity_groups = find_duplicate_entity_groups(session, user_id=user_id)
        report.superseded_memories = _superseded_memory_count(session, user_id=user_id)
        if reindex:
            stats = reindex_vectors(
                session=session,
                user_id=user_id,
                include_private=include_private,
                reset=True,
            )
            report.reindex = asdict(stats)
        return report
    finally:
        if owned_session:
            session.close()


def find_duplicate_entity_groups(session: Session, *, user_id: str | None = None) -> list[list[str]]:
    query = session.query(Entity)
    if user_id:
        query = query.filter(Entity.user_id == user_id)
    buckets: dict[tuple[str, str], list[Entity]] = {}
    for entity in query.order_by(Entity.type, Entity.canonical_name).all():
        key = (entity.type, _normal_name(entity.canonical_name))
        buckets.setdefault(key, []).append(entity)
    groups = []
    for entities in buckets.values():
        if len(entities) > 1:
            groups.append([f"{entity.canonical_name}:{entity.id[:10]}" for entity in entities])
    return groups


def _superseded_memory_count(session: Session, *, user_id: str | None = None) -> int:
    query = session.query(Memory).filter(Memory.valid_to.is_not(None))
    if user_id:
        query = query.filter(Memory.user_id == user_id)
    return int(query.count() or 0)


def _normal_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
