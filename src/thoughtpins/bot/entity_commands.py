"""Telegram entity commands and graph cleanup operations."""

from __future__ import annotations

import re

from loguru import logger

from thoughtpins.bot.utils import parse_limit, telegram_user_id, trim_for_telegram
from thoughtpins.db import (
    Entity,
    EventParticipant,
    Memory,
    Relationship,
)
from thoughtpins.memory.entity_stats import entity_reference_counts as _entity_reference_counts
from thoughtpins.memory.store import MemoryStore
from thoughtpins.store import get_session


def _scope_user(query, model, user_id: str | None):
    if user_id:
        return query.filter(model.user_id == user_id)
    return query


async def cmd_person(update, context) -> None:
    """Show person profile summary."""
    name = " ".join(context.args) if context.args else ""
    if not name:
        await update.message.reply_text("Usage: /person <name>")
        return

    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        store = MemoryStore(session, user_id=user_id)
        entity = store.get_entity_by_name(name, "person")
        if not entity:
            entity = store.get_entity_by_name(name)
        if not entity:
            await update.message.reply_text(f"No records found for '{name}'.")
            return

        memories = store.get_memories_by_entity(entity.id, limit=10)
        rels = store.get_relationships_for_entity(entity.id)
        attrs = entity.attributes_json or []

        lines = [f"Person: {entity.canonical_name}", f"ID: {entity.id}", ""]
        if attrs:
            lines.append("Attributes:")
            for attr in attrs[:10]:
                lines.append(f"  - {attr['key']}: {attr['value']}")
        lines.append(f"\nRecent memories ({len(memories)}):")
        for memory in memories[:5]:
            lines.append(f"  - [{memory.local_date}] {memory.text[:150]}")

        if rels:
            lines.append(f"\nRelationships ({len(rels)}):")
            for rel in rels[:5]:
                other = rel.target_entity if rel.source_entity_id == entity.id else rel.source_entity
                if other:
                    lines.append(f"  - {rel.relation_type} -> {other.canonical_name}")

        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()


async def cmd_place(update, context) -> None:
    """Show place history."""
    name = " ".join(context.args) if context.args else ""
    if not name:
        await update.message.reply_text("Usage: /place <name>")
        return

    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        store = MemoryStore(session, user_id=user_id)
        events = store.get_events_by_place(name, limit=10)
        if not events:
            await update.message.reply_text(f"No visits recorded for '{name}'.")
            return

        lines = [f"Place: {name}", f"Visits: {len(events)}\n"]
        for event in events:
            participants = store.get_event_participants(event.id)
            participant_names = [participant[0].canonical_name for participant in participants]
            lines.append(f"- {event.local_date} - {event.name}")
            lines.append(f"  With: {', '.join(participant_names) if participant_names else 'unknown'}")
            if event.summary:
                lines.append(f"  {event.summary[:200]}")

        await update.message.reply_text("\n".join(lines))
    finally:
        session.close()


def _normal_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().removeprefix("the ").strip())


def _entity_aliases(entity: Entity) -> list[str]:
    aliases = entity.aliases_json or []
    return [str(alias).strip() for alias in aliases if str(alias).strip()]


def _find_entity_candidates(
    session,
    user_id: str,
    name: str,
    *,
    entity_type: str | None = None,
) -> list[Entity]:
    needle = _normal_name(name)
    if not needle:
        return []

    query = _scope_user(session.query(Entity), Entity, user_id)
    if entity_type:
        query = query.filter(Entity.type == entity_type)
    entities = query.order_by(Entity.type, Entity.canonical_name).all()

    exact: list[Entity] = []
    partial: list[Entity] = []
    for entity in entities:
        names = [entity.canonical_name, *_entity_aliases(entity)]
        normalized = [_normal_name(item) for item in names]
        if needle in normalized:
            exact.append(entity)
        elif any(needle in item for item in normalized):
            partial.append(entity)
    return exact or partial


def _resolve_single_entity(
    session,
    user_id: str,
    name: str,
    *,
    entity_type: str | None = None,
) -> tuple[Entity | None, str | None]:
    candidates = _find_entity_candidates(session, user_id, name, entity_type=entity_type)
    if not candidates:
        return None, f"No entity found for '{name}'."
    if len(candidates) == 1:
        return candidates[0], None
    names = ", ".join(f"{item.canonical_name} [{item.type}]" for item in candidates[:8])
    suffix = "" if len(candidates) <= 8 else f", and {len(candidates) - 8} more"
    return None, f"Multiple entities matched '{name}': {names}{suffix}. Use a more exact name."


async def _send_entity_catalog(update, context, *, mode: str) -> None:
    from thoughtpins.bot.disclosure import is_disclosure_mode

    args = context.args or []
    limit = parse_limit(args, default=30 if mode != "concepts" else 40, maximum=100)
    chat_id = str(update.message.chat_id)
    include_private = is_disclosure_mode(chat_id)

    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        query = _scope_user(session.query(Entity), Entity, user_id)
        if mode == "people":
            query = query.filter(Entity.type == "person")
            title = "People"
        elif mode == "places":
            query = query.filter(Entity.type == "place")
            title = "Places"
        else:
            query = query.filter(Entity.type.notin_(["person", "place"]))
            title = "Concepts and other entities"

        rows: list[tuple[Entity, dict[str, int]]] = []
        for entity in query.order_by(Entity.canonical_name).all():
            counts = _entity_reference_counts(session, entity.id, user_id, include_private=include_private)
            if include_private or counts["total"] > 0:
                rows.append((entity, counts))
        rows.sort(key=lambda item: (-item[1]["total"], item[0].canonical_name.lower()))

        if not rows:
            await update.message.reply_text(f"No {title.lower()} found yet.")
            return

        private_note = "including confidential entries" if include_private else "public entries only"
        lines = [f"{title} ({len(rows)} total, showing {min(limit, len(rows))}; {private_note})"]
        for entity, counts in rows[:limit]:
            aliases = _entity_aliases(entity)
            alias_text = f"; aliases: {', '.join(aliases[:3])}" if aliases else ""
            if mode == "places":
                detail = (
                    f"visits={counts['place_events']}, memories={counts['memories']}, "
                    f"expenses={counts['expenses']}, links={counts['links']}"
                )
            elif mode == "people":
                detail = (
                    f"memories={counts['memories']}, links={counts['links']}, "
                    f"events={counts['participations']}, actions={counts['actions']}"
                )
            else:
                detail = (
                    f"type={entity.type}, memories={counts['memories']}, links={counts['links']}, "
                    f"mentions={counts['mentions']}"
                )
            lines.append(f"- {entity.canonical_name} ({detail}; id={entity.id[:8]}{alias_text})")

        await update.message.reply_text(trim_for_telegram("\n".join(lines)))
    finally:
        session.close()


async def cmd_people(update, context) -> None:
    """List people in the memory graph."""
    await _send_entity_catalog(update, context, mode="people")


async def cmd_places(update, context) -> None:
    """List places in the memory graph."""
    await _send_entity_catalog(update, context, mode="places")


async def cmd_concepts(update, context) -> None:
    """List non-person/place entities in the memory graph."""
    await _send_entity_catalog(update, context, mode="concepts")


def _parse_rename_text(text: str) -> tuple[str, str] | None:
    for separator in ("->", "=>", "|"):
        if separator in text:
            old, new = text.split(separator, 1)
            old = old.strip().strip("'\"")
            new = new.strip().strip("'\"")
            if old and new:
                return old, new
    return None


async def cmd_rename(update, context) -> None:
    """Rename an entity while preserving the old name as an alias."""
    text = " ".join(context.args) if context.args else ""
    parsed = _parse_rename_text(text)
    if not parsed:
        await update.message.reply_text(
            "Usage: /rename <old name> -> <new name>\nExample: /rename The Green Bar -> The Greene Bar"
        )
        return

    old_name, new_name = parsed
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        entity, error = _resolve_single_entity(session, user_id, old_name)
        if error or entity is None:
            await update.message.reply_text(error or "Entity not found.")
            return

        existing, _existing_error = _resolve_single_entity(session, user_id, new_name)
        if existing and existing.id != entity.id and _normal_name(existing.canonical_name) == _normal_name(new_name):
            await update.message.reply_text(
                f"'{new_name}' already exists as {existing.canonical_name} [{existing.type}]. "
                f"Use /merge '{existing.canonical_name}' '{entity.canonical_name}' if they are the same thing."
            )
            return

        aliases = _entity_aliases(entity)
        old_canonical = entity.canonical_name
        for alias in [old_canonical, old_name]:
            if _normal_name(alias) != _normal_name(new_name) and alias not in aliases:
                aliases.append(alias)
        entity.canonical_name = new_name
        entity.aliases_json = aliases
        session.commit()

        await update.message.reply_text(f"Renamed '{old_canonical}' -> '{new_name}'. Old name kept as an alias.")
    finally:
        session.close()


def _find_memory_by_ref(session, user_id: str, reference: str) -> tuple[Memory | None, str | None]:
    reference = reference.strip()
    if not reference:
        return None, "Missing memory id."

    exact = _scope_user(session.query(Memory), Memory, user_id).filter(Memory.id == reference).first()
    if exact:
        return exact, None
    if len(reference) < 6:
        return None, "Use at least 6 characters of a memory id."

    matches = (
        _scope_user(session.query(Memory), Memory, user_id)
        .filter(Memory.id.ilike(f"{reference}%"))
        .order_by(Memory.created_at_utc.desc())
        .limit(10)
        .all()
    )
    if not matches:
        return None, f"No memory found for id prefix '{reference}'."
    if len(matches) > 1:
        ids = ", ".join(memory.id[:10] for memory in matches)
        return None, f"Multiple memories matched '{reference}': {ids}. Use a longer id."
    return matches[0], None


def _delete_memory_vector(memory_id: str) -> None:
    try:
        from thoughtpins.memory.vector_store import get_vector_store

        get_vector_store().delete([memory_id])
    except Exception as exc:
        logger.warning("Could not delete memory {} from vector index: {}", memory_id, exc)


async def cmd_forget(update, context) -> None:
    """Safely remove a single memory, or an orphan entity with no references."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "Usage: /forget memory <memory_id>\n"
            "Or: /forget entity <entity name>\n"
            "Entity deletion only works when it has no memory/event/link references."
        )
        return

    mode = ""
    target = text.strip()
    lower = target.lower()
    if lower.startswith("memory "):
        mode = "memory"
        target = target[7:].strip()
    elif lower.startswith("entity "):
        mode = "entity"
        target = target[7:].strip()

    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        memory = None
        memory_error = None
        if mode in {"", "memory"}:
            memory, memory_error = _find_memory_by_ref(session, user_id, target)
        if memory:
            memory_id = memory.id
            text_preview = memory.text[:140]
            deleted_relationships = (
                _scope_user(session.query(Relationship), Relationship, user_id)
                .filter(Relationship.memory_id == memory_id)
                .delete(synchronize_session=False)
            )
            session.delete(memory)
            session.commit()
            _delete_memory_vector(memory_id)
            await update.message.reply_text(
                f"Forgot memory {memory_id[:10]} and {deleted_relationships} linked relationship rows.\n"
                f"Preview: {text_preview}"
            )
            return
        if mode == "memory":
            await update.message.reply_text(memory_error or "Memory not found.")
            return

        entity, entity_error = _resolve_single_entity(session, user_id, target)
        if entity is None:
            await update.message.reply_text(entity_error or memory_error or "Nothing matched that target.")
            return
        counts = _entity_reference_counts(session, entity.id, user_id, include_private=True)
        if counts["total"] > 0:
            await update.message.reply_text(
                f"Refusing to delete '{entity.canonical_name}' because it still has references: "
                f"{counts['memories']} memories, {counts['links']} links, "
                f"{counts['participations'] + counts['place_events']} events, "
                f"{counts['actions']} actions, {counts['expenses']} expenses, "
                f"{counts['mentions']} mentions. Use /merge for duplicates or /forget memory <id> for a single fact."
            )
            return
        canonical = entity.canonical_name
        session.delete(entity)
        session.commit()
        await update.message.reply_text(f"Forgot orphan entity '{canonical}'.")
    finally:
        session.close()


def _parse_merge_names(args: list[str]) -> list[str]:
    text = " ".join(args)
    parts = re.findall(r"'([^']*)'|\"([^\"]*)\"|(\S+)", text)
    names: list[str] = []
    for part in parts:
        name = part[0] or part[1] or part[2]
        if name:
            names.append(name)
    return names


async def cmd_merge(update, context) -> None:
    """Merge two entities into one, preserving memories and relationships."""
    args = context.args if context.args else []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /merge <keep_name> <merge_name>\n"
            "Merges the second entity into the first, preserving all memories and relationships.\n"
            "Example: /merge 'CFA' 'CFA exam'"
        )
        return

    names = _parse_merge_names(args)
    if len(names) < 2:
        await update.message.reply_text("Need two entity names. Use quotes for multi-word names.")
        return

    keep_name = names[0]
    merge_name = names[1]

    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        keep = (
            session.query(Entity)
            .filter(
                Entity.user_id == user_id,
                Entity.canonical_name == keep_name,
            )
            .first()
        )
        merge = (
            session.query(Entity)
            .filter(
                Entity.user_id == user_id,
                Entity.canonical_name == merge_name,
            )
            .first()
        )

        if not keep:
            keep = (
                session.query(Entity)
                .filter(
                    Entity.user_id == user_id,
                    Entity.canonical_name.ilike(f"%{keep_name}%"),
                )
                .first()
            )
        if not merge:
            merge = (
                session.query(Entity)
                .filter(
                    Entity.user_id == user_id,
                    Entity.canonical_name.ilike(f"%{merge_name}%"),
                )
                .first()
            )

        if not keep or not merge:
            await update.message.reply_text(
                f"Could not find both entities. Found: keep={'yes' if keep else 'no'}, merge={'yes' if merge else 'no'}"
            )
            return

        count = 0
        for memory in (
            session.query(Memory)
            .filter(
                Memory.user_id == user_id,
                (Memory.subject_entity_id == merge.id) | (Memory.object_entity_id == merge.id),
            )
            .all()
        ):
            if memory.subject_entity_id == merge.id:
                memory.subject_entity_id = keep.id
                count += 1
            if memory.object_entity_id == merge.id:
                memory.object_entity_id = keep.id
                count += 1

        for relationship in (
            session.query(Relationship)
            .filter(
                Relationship.user_id == user_id,
                (Relationship.source_entity_id == merge.id) | (Relationship.target_entity_id == merge.id),
            )
            .all()
        ):
            if relationship.source_entity_id == merge.id:
                relationship.source_entity_id = keep.id
                count += 1
            if relationship.target_entity_id == merge.id:
                relationship.target_entity_id = keep.id
                count += 1

        for participant in (
            session.query(EventParticipant)
            .filter(
                EventParticipant.user_id == user_id,
                EventParticipant.entity_id == merge.id,
            )
            .all()
        ):
            participant.entity_id = keep.id
            count += 1

        keep_aliases = keep.aliases_json or []
        merge_aliases = merge.aliases_json or []
        for alias in merge_aliases + [merge.canonical_name]:
            if alias not in keep_aliases and alias != keep.canonical_name:
                keep_aliases.append(alias)
        keep.aliases_json = keep_aliases

        session.delete(merge)
        session.commit()

        await update.message.reply_text(
            f"Merged '{merge_name}' into '{keep.canonical_name}'.\nUpdated {count} references. Aliases preserved."
        )
    finally:
        session.close()
