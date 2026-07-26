"""Persistence boundary for validated journal extraction results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.db import (
    ActionItem,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    Memory,
    RawEntry,
    Relationship,
)
from thoughtpins.ingestion.entity_resolution import create_or_get_entity
from thoughtpins.ingestion.normalization import canonical_guess
from thoughtpins.ingestion.postprocess import (
    _dedupe_extracted_action_items,
    _dedupe_extracted_memories,
    _missing_relationship_entity_type,
    _pick_max_sensitivity,
    _rel_weight,
)
from thoughtpins.llm import ExtractionResult
from thoughtpins.memory.ontology import normalize_entity_type, relationship_allowed
from thoughtpins.utils import parse_relative_date


@dataclass
class ExtractionWriter:
    """Write one extraction atomically through a single tenant-scoped context."""

    session: Session
    raw_entry: RawEntry
    local_date: date
    raw_text: str = ""
    entity_map: dict[str, Entity] = field(default_factory=dict)
    stats: dict[str, int] = field(
        default_factory=lambda: {
            "entities": 0,
            "events": 0,
            "memories": 0,
            "relationships": 0,
            "action_items": 0,
            "expenses": 0,
        }
    )

    @property
    def user_id(self) -> str:
        return self.raw_entry.user_id

    def write(self, extraction: ExtractionResult) -> dict[str, int]:
        self._write_entities(extraction)
        self._ensure_user_entity()
        self._write_events(extraction)
        self._write_memories(extraction)
        self._write_attributed_quotes(extraction)
        self._write_relationships(extraction)
        self._write_action_items(extraction)
        self._write_expenses(extraction)
        self._write_social_dynamics(extraction)
        self._write_timeline(extraction)
        return self.stats

    def _write_entities(self, extraction: ExtractionResult) -> None:
        for extracted in extraction.entities:
            entity = create_or_get_entity(
                self.session,
                extracted.surface_name,
                canonical_guess(extracted.canonical_guess or extracted.surface_name),
                normalize_entity_type(extracted.type),
                sensitivity=_pick_max_sensitivity([attribute.sensitivity for attribute in extracted.attributes]),
                confidence="observed_by_user",
                raw_text=self.raw_text,
                user_id=self.user_id,
            )
            self.entity_map[extracted.surface_name] = entity
            attributes = list(entity.attributes_json or [])
            attributes.extend(
                {
                    "key": attribute.key,
                    "value": attribute.value,
                    "confidence": attribute.confidence,
                    "sensitivity": attribute.sensitivity,
                    "temporal_scope": attribute.temporal_scope,
                    "source_entry_id": self.raw_entry.id,
                }
                for attribute in extracted.attributes
            )
            entity.attributes_json = attributes
            self.session.add(
                EntityMention(
                    user_id=self.user_id,
                    raw_entry_id=self.raw_entry.id,
                    entity_id=entity.id,
                    surface_text=extracted.surface_name,
                    mention_context=extraction.entry_summary[:500] if extraction.entry_summary else "",
                    confidence="observed_by_user",
                )
            )
            self.stats["entities"] += 1

    def _ensure_user_entity(self) -> None:
        if "user" in self.entity_map or "me" in self.entity_map:
            return
        entity = create_or_get_entity(self.session, "user", "User", "person", user_id=self.user_id)
        self.entity_map.update({"user": entity, "me": entity, "i": entity})

    def _write_events(self, extraction: ExtractionResult) -> None:
        for extracted in extraction.events:
            place_id = None
            if extracted.place:
                place = create_or_get_entity(
                    self.session,
                    extracted.place,
                    extracted.place,
                    "place",
                    sensitivity=extracted.sensitivity,
                    raw_text=self.raw_text,
                    user_id=self.user_id,
                )
                self.entity_map.setdefault(extracted.place, place)
                place_id = place.id
            event = Event(
                user_id=self.user_id,
                name=extracted.name,
                event_type=extracted.event_type,
                local_date=self.local_date,
                place_entity_id=place_id,
                summary=extracted.summary,
                sensitivity=extracted.sensitivity,
                source_raw_entry_id=self.raw_entry.id,
            )
            self.session.add(event)
            self.session.flush()
            self.stats["events"] += 1
            for participant in extracted.participants:
                entity, role = self._participant(participant)
                if entity is not None:
                    self.session.add(
                        EventParticipant(
                            user_id=self.user_id,
                            event_id=event.id,
                            entity_id=entity.id,
                            role=role,
                        )
                    )

    def _participant(self, name: str) -> tuple[Entity | None, str]:
        normalized = name.strip().lower()
        if normalized in {"i", "me", "user"}:
            return self.entity_map.get("user"), "user"
        entity = self.entity_map.get(name)
        if entity is None:
            entity = create_or_get_entity(
                self.session,
                name,
                canonical_guess(name),
                "person",
                raw_text=self.raw_text,
                user_id=self.user_id,
            )
            self.entity_map[name] = entity
        return entity, "attendee"

    def _write_memories(self, extraction: ExtractionResult) -> None:
        for extracted in _dedupe_extracted_memories(extraction.memories):
            subject = self._memory_subject(extracted.subject)
            obj = self.entity_map.get(extracted.object) if extracted.object else None
            occurred_start, occurred_end = self._relative_range(extracted.relative_date)
            self.session.add(
                Memory(
                    user_id=self.user_id,
                    raw_entry_id=self.raw_entry.id,
                    memory_type=extracted.memory_type,
                    subject_entity_id=subject.id if subject else None,
                    object_entity_id=obj.id if obj else None,
                    predicate=extracted.predicate,
                    text=extracted.text,
                    structured_json=extracted.model_dump() if hasattr(extracted, "model_dump") else None,
                    occurred_at_start=occurred_start,
                    occurred_at_end=occurred_end,
                    local_date=self.local_date,
                    sensitivity=extracted.sensitivity,
                    confidence=extracted.confidence,
                    source_provenance=f"raw_entry:{self.raw_entry.id}",
                    created_at_utc=self.raw_entry.created_at_utc,
                )
            )
            self.stats["memories"] += 1

    def _memory_subject(self, name: str | None) -> Entity | None:
        if not name:
            return None
        entity = self.entity_map.get(name)
        if entity is None and name.lower() not in {"i", "me", "user"}:
            entity = create_or_get_entity(
                self.session,
                name,
                canonical_guess(name),
                "person",
                raw_text=self.raw_text,
                user_id=self.user_id,
            )
            self.entity_map[name] = entity
        return entity

    def _write_attributed_quotes(self, extraction: ExtractionResult) -> None:
        stored_quotes = {
            memory.text.strip().casefold()
            for memory in extraction.memories
            if memory.memory_type.strip().lower() == "quote"
        }
        for quote in extraction.attributed_quotes:
            quote_text = quote.quote.strip()
            if not quote_text or quote_text.casefold() in stored_quotes:
                continue
            speaker = self._memory_subject(quote.speaker)
            metadata = quote.model_dump(mode="json")
            metadata.update(
                {
                    "attributed_to": quote.speaker,
                    "people_involved": [quote.speaker, *quote.people_discussed],
                }
            )
            label = "said" if quote.is_exact else "was recorded as saying"
            self.session.add(
                Memory(
                    user_id=self.user_id,
                    raw_entry_id=self.raw_entry.id,
                    memory_type="quote",
                    subject_entity_id=speaker.id if speaker else None,
                    predicate="said",
                    text=f'{quote.speaker} {label}: "{quote_text}"',
                    structured_json=metadata,
                    local_date=self.local_date,
                    sensitivity="personal",
                    confidence=quote.confidence,
                    source_provenance=f"raw_entry:{self.raw_entry.id}",
                    created_at_utc=self.raw_entry.created_at_utc,
                )
            )
            stored_quotes.add(quote_text.casefold())
            self.stats["memories"] += 1
            self.stats["attributed_quotes"] = self.stats.get("attributed_quotes", 0) + 1

    def _relative_range(self, expression: str | None) -> tuple[datetime | None, datetime | None]:
        if not expression:
            return None, None
        parsed = parse_relative_date(expression, self.local_date)
        start = datetime.fromisoformat(parsed["inferred_start"]) if parsed.get("inferred_start") else None
        end = datetime.fromisoformat(parsed["inferred_end"]) if parsed.get("inferred_end") else None
        return start, end

    def _write_relationships(self, extraction: ExtractionResult) -> None:
        for extracted in extraction.relationships:
            source = self.entity_map.get(extracted.source)
            target = self.entity_map.get(extracted.target)
            source_type = normalize_entity_type(
                source.type if source else _missing_relationship_entity_type(extracted.relation_type, source=True)
            )
            target_type = normalize_entity_type(
                target.type if target else _missing_relationship_entity_type(extracted.relation_type, source=False)
            )
            decision = relationship_allowed(extracted.relation_type, source_type, target_type)
            if not decision.allowed:
                logger.debug(
                    "Skipping relationship outside ontology: {} -{}-> {} ({})",
                    extracted.source,
                    extracted.relation_type,
                    extracted.target,
                    decision.reason,
                )
                continue
            source = source or self._relationship_entity(extracted.source, source_type)
            target = target or self._relationship_entity(extracted.target, target_type)
            self.session.add(
                Relationship(
                    user_id=self.user_id,
                    source_entity_id=source.id,
                    target_entity_id=target.id,
                    relation_type=decision.relation_type,
                    raw_entry_id=self.raw_entry.id,
                    weight=_rel_weight(decision.relation_type),
                    confidence=extracted.confidence,
                    sensitivity=extracted.sensitivity,
                    first_seen_at=self.raw_entry.created_at_utc,
                    last_seen_at=self.raw_entry.created_at_utc,
                    evidence_count=1,
                )
            )
            self.stats["relationships"] += 1

    def _relationship_entity(self, name: str, entity_type: str) -> Entity:
        entity = create_or_get_entity(
            self.session,
            name,
            canonical_guess(name),
            entity_type,
            raw_text=self.raw_text,
            user_id=self.user_id,
        )
        self.entity_map[name] = entity
        return entity

    def _write_action_items(self, extraction: ExtractionResult) -> None:
        items = _dedupe_extracted_action_items(
            extraction.action_items,
            raw_text=self.raw_text,
            local_date=self.local_date,
        )
        for extracted, due_at in items:
            self.session.add(
                ActionItem(
                    user_id=self.user_id,
                    raw_entry_id=self.raw_entry.id,
                    description=extracted.description,
                    due_at=due_at,
                    status=extracted.status,
                    sensitivity=extracted.sensitivity,
                )
            )
            self.stats["action_items"] += 1

    def _write_expenses(self, extraction: ExtractionResult) -> None:
        for extracted in extraction.expenses:
            merchant_id = None
            if extracted.merchant_or_place:
                merchant = create_or_get_entity(
                    self.session,
                    extracted.merchant_or_place,
                    canonical_guess(extracted.merchant_or_place),
                    "place",
                    raw_text=self.raw_text,
                    user_id=self.user_id,
                )
                merchant_id = merchant.id
            self.session.add(
                Expense(
                    user_id=self.user_id,
                    raw_entry_id=self.raw_entry.id,
                    amount=extracted.amount,
                    currency=extracted.currency,
                    merchant_or_place_entity_id=merchant_id,
                    reason=extracted.reason,
                    category=extracted.category,
                    confidence=extracted.confidence,
                )
            )
            self.stats["expenses"] += 1

    def _write_social_dynamics(self, extraction: ExtractionResult) -> None:
        for dynamic in extraction.social_dynamics:
            if not dynamic.description:
                continue
            text = dynamic.description
            if dynamic.significance:
                text += f" Significance: {dynamic.significance}"
            self._write_derived_memory("social_dynamic", text, dynamic)
            self.stats["social_dynamics"] = self.stats.get("social_dynamics", 0) + 1

    def _write_timeline(self, extraction: ExtractionResult) -> None:
        for item in extraction.timeline_items:
            if not item.description:
                continue
            text = f"[{item.relative_position}] {item.description}"
            if item.related_to:
                text += f" (re: {item.related_to})"
            if item.temporal_expression:
                text += f" [{item.temporal_expression}]"
            self._write_derived_memory("progress_update", text, item)
            self.stats["timeline_items"] = self.stats.get("timeline_items", 0) + 1

    def _write_derived_memory(self, memory_type: str, text: str, source: object) -> None:
        confidence = str(getattr(source, "confidence", "observed_by_user") or "observed_by_user")
        sensitivity = str(getattr(source, "sensitivity", "personal") or "personal")
        self.session.add(
            Memory(
                user_id=self.user_id,
                raw_entry_id=self.raw_entry.id,
                memory_type=memory_type,
                text=text,
                local_date=self.local_date,
                sensitivity=sensitivity,
                confidence=confidence,
                source_provenance=f"raw_entry:{self.raw_entry.id}",
                structured_json=source.model_dump() if hasattr(source, "model_dump") else None,
            )
        )


def store_extraction(
    session: Session,
    raw_entry: RawEntry,
    extraction: ExtractionResult,
    local_date: date,
    raw_text: str = "",
) -> dict[str, int]:
    return ExtractionWriter(session, raw_entry, local_date, raw_text).write(extraction)
