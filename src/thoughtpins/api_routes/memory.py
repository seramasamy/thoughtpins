"""Memory navigation, entity-card, and context-inspection routes."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_

from thoughtpins.api_contracts import StatsResponse
from thoughtpins.api_memory_cards import (
    EVENT_CARD_SECTIONS,
    MEMORY_CARD_SECTIONS,
    MemoryCardDetailResponse,
    MemoryCardResponse,
    MemoryCardsResponse,
    event_card,
    event_card_detail,
    memory_card,
    memory_card_detail,
)
from thoughtpins.chat.personality import PREDEFINED, get_active_profile, load_personality
from thoughtpins.config import config
from thoughtpins.db import Entity, Event
from thoughtpins.memory.audit import audit_memory_system
from thoughtpins.memory.context_package import build_memory_context_package
from thoughtpins.memory.full_context import build_full_context, build_navigational_map
from thoughtpins.memory.store import MemoryStore
from thoughtpins.store import get_session


def create_memory_router(
    *,
    current_user_dependency: Callable[..., str],
    start_time: float,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/memory/audit")
    async def memory_audit(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        session = get_session()
        try:
            return audit_memory_system(session, user_id=user_id).as_dict()
        finally:
            session.close()

    @router.get("/status", response_model=StatsResponse)
    @router.get("/v1/status", response_model=StatsResponse)
    async def status(user_id: str = Depends(current_user_dependency)) -> StatsResponse:
        session = get_session()
        try:
            stats = MemoryStore(session, user_id=user_id).get_stats()
            vault = config.vault_path()
            vault_files = len(list(vault.rglob("*.md"))) if vault.exists() else 0
            return StatsResponse(
                **stats,
                uptime_seconds=round(time.time() - start_time, 1),
                vault_files=vault_files,
            )
        finally:
            session.close()

    @router.get("/v1/memory/cards", response_model=MemoryCardsResponse)
    async def memory_cards(
        section: str = Query("people", pattern="^(people|places|projects|organizations|concepts|events|things|all)$"),
        q: str = Query(
            "",
            max_length=128,
            description="Optional case-insensitive search over entity names, notes, and event summaries",
        ),
        limit: int = Query(24, ge=1, le=100),
        user_id: str = Depends(current_user_dependency),
    ) -> MemoryCardsResponse:
        entity_types = MEMORY_CARD_SECTIONS[section]
        search = q.strip()
        session = get_session()
        try:
            query = session.query(Entity).filter(Entity.user_id == user_id, Entity.type.in_(entity_types))
            if search:
                pattern = f"%{search}%"
                query = query.filter(
                    or_(
                        Entity.canonical_name.ilike(pattern),
                        Entity.type.ilike(pattern),
                        Entity.notes.ilike(pattern),
                    )
                )
            entities = (
                query.order_by(
                    func.coalesce(Entity.salience_score, 0.0).desc(),
                    Entity.updated_at_utc.desc(),
                    Entity.canonical_name.asc(),
                )
                .limit(limit)
                .all()
            )
            items: list[MemoryCardResponse] = [memory_card(entity, session) for entity in entities]

            if section in EVENT_CARD_SECTIONS and len(items) < limit:
                event_query = session.query(Event).filter(Event.user_id == user_id)
                if search:
                    pattern = f"%{search}%"
                    event_query = event_query.filter(
                        or_(
                            Event.name.ilike(pattern),
                            Event.event_type.ilike(pattern),
                            Event.summary.ilike(pattern),
                        )
                    )
                events = (
                    event_query.order_by(Event.local_date.desc(), Event.start_at.desc(), Event.name.asc())
                    .limit(limit - len(items))
                    .all()
                )
                items.extend(event_card(event, session) for event in events)

            return MemoryCardsResponse(
                section=section,
                query=search,
                sections=MEMORY_CARD_SECTIONS,
                items=items[:limit],
                total=len(items),
            )
        finally:
            session.close()

    @router.get("/v1/memory/cards/{entity_id}", response_model=MemoryCardDetailResponse)
    async def get_memory_card(
        entity_id: str,
        user_id: str = Depends(current_user_dependency),
    ) -> MemoryCardDetailResponse:
        session = get_session()
        try:
            if entity_id.startswith("event:"):
                event_ref = entity_id.split(":", 1)[1]
                event = session.query(Event).filter(Event.user_id == user_id, Event.id == event_ref).first()
                if not event:
                    raise HTTPException(status_code=404, detail="Memory card not found")
                return event_card_detail(event, session)

            entity = session.query(Entity).filter(Entity.user_id == user_id, Entity.id == entity_id).first()
            if entity:
                return memory_card_detail(entity, session)

            event = session.query(Event).filter(Event.user_id == user_id, Event.id == entity_id).first()
            if event:
                return event_card_detail(event, session)
            raise HTTPException(status_code=404, detail="Memory card not found")
        finally:
            session.close()

    @router.get("/person/{name}")
    @router.get("/v1/people/{name}")
    async def person(
        name: str,
        user_id: str = Depends(current_user_dependency),
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")

        session = get_session()
        try:
            store = MemoryStore(session, user_id=user_id)
            entity = store.get_entity_by_name(name, "person") or store.get_entity_by_name(name)
            if not entity:
                raise HTTPException(status_code=404, detail=f"No records for '{name}'")

            memories = store.get_memories_by_entity(entity.id, limit=20)
            relationships = store.get_relationships_for_entity(entity.id)
            return {
                "name": entity.canonical_name,
                "entity_id": entity.id,
                "type": entity.type,
                "attributes": entity.attributes_json or [],
                "recent_memories": [
                    {
                        "date": str(memory.local_date),
                        "type": memory.memory_type,
                        "text": memory.text,
                        "confidence": memory.confidence,
                    }
                    for memory in memories[:15]
                ],
                "relationships": [
                    {
                        "type": relationship.relation_type,
                        "other": (
                            relationship.target_entity.canonical_name
                            if relationship.target_entity and relationship.source_entity_id == entity.id
                            else relationship.source_entity.canonical_name
                            if relationship.source_entity
                            else "unknown"
                        ),
                        "confidence": relationship.confidence,
                    }
                    for relationship in relationships[:15]
                ],
                "memory_count": len(memories),
                "relationship_count": len(relationships),
            }
        finally:
            session.close()

    @router.get("/place/{name}")
    @router.get("/v1/places/{name}")
    async def place(name: str, user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")

        session = get_session()
        try:
            store = MemoryStore(session, user_id=user_id)
            events = store.get_events_by_place(name, limit=20)
            return {
                "name": name,
                "visits": len(events),
                "events": [
                    {
                        "date": str(event.local_date),
                        "name": event.name,
                        "type": event.event_type,
                        "summary": event.summary,
                        "participants": [
                            participant[0].canonical_name for participant in store.get_event_participants(event.id)
                        ],
                    }
                    for event in events
                ],
            }
        finally:
            session.close()

    @router.get("/personality")
    @router.get("/v1/personality")
    async def get_personality(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        profile = get_active_profile()
        return {
            "user_id": user_id,
            "current": load_personality(),
            "profile": {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description,
            },
            "available": {
                pid: {"name": item.name, "description": item.description} for pid, item in PREDEFINED.items()
            },
        }

    @router.get("/context")
    @router.get("/v1/context")
    async def get_context(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        session = get_session()
        try:
            navigation = build_navigational_map(session, user_id=user_id)
            full = build_full_context(session, user_id=user_id)
            active = build_memory_context_package("", session, user_id=user_id)
            return {
                "memory_context_mode": config.MEMORY_CONTEXT_MODE,
                "navigational_map_chars": len(navigation),
                "full_context_chars": len(full),
                "active_context_chars": len(active),
                "navigational_map": navigation,
                "full_context": full,
                "active_context": active,
            }
        finally:
            session.close()

    return router
