from __future__ import annotations

from datetime import datetime


def test_memory_cards_expose_events_things_concepts_and_sources(isolated_db):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app
    from thoughtpins.db import DocumentSource, Entity, EntityMention, Event, EventParticipant, Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 6, 30, 18, 15),
            local_date=datetime(2026, 6, 30).date(),
            local_time="18:15",
            source="test",
            raw_text="Dinner with Maya at Koyo. She gave me the brass compass token and we discussed attention architecture.",
            content_hash=hash_text("memory cards fixture"),
            processed_status="completed",
        )
        session.add(raw)
        session.flush()

        maya = Entity(user_id=user.id, type="person", canonical_name="Maya")
        koyo = Entity(user_id=user.id, type="place", canonical_name="Koyo")
        compass = Entity(user_id=user.id, type="thing", canonical_name="Brass Compass", aliases_json=["compass token"])
        attention = Entity(user_id=user.id, type="concept", canonical_name="Attention Architecture")
        session.add_all([maya, koyo, compass, attention])
        session.flush()
        session.add_all(
            [
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=maya.id, surface_text="Maya"),
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=koyo.id, surface_text="Koyo"),
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=compass.id, surface_text="brass compass"),
                EntityMention(
                    user_id=user.id, raw_entry_id=raw.id, entity_id=attention.id, surface_text="attention architecture"
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="object",
                    subject_entity_id=compass.id,
                    object_entity_id=attention.id,
                    text="Maya gave the user a brass compass token connected to attention architecture.",
                    local_date=raw.local_date,
                    created_at_utc=raw.created_at_utc,
                    confidence="observed_by_user",
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="concept",
                    subject_entity_id=attention.id,
                    text="Attention Architecture is a concept the user discussed at Koyo.",
                    local_date=raw.local_date,
                    created_at_utc=raw.created_at_utc,
                    confidence="observed_by_user",
                ),
            ]
        )
        doc = DocumentSource(
            user_id=user.id,
            raw_entry_id=raw.id,
            source_type="article",
            title="Attention Architecture Notes",
            source_url="https://example.com/attention-architecture",
            content_hash=hash_text("attention architecture notes"),
            raw_text="Attention architecture source text.",
            summary="A source about attention architecture.",
            status="processed",
            local_date=raw.local_date,
            access_method="user_paste",
            rights_basis="user_provided",
        )
        session.add(doc)
        event = Event(
            user_id=user.id,
            name="Dinner at Koyo With Maya",
            event_type="meal",
            local_date=raw.local_date,
            place_entity_id=koyo.id,
            summary="Maya gave the user the brass compass token during dinner at Koyo.",
            source_raw_entry_id=raw.id,
        )
        session.add(event)
        session.flush()
        session.add(EventParticipant(user_id=user.id, event_id=event.id, entity_id=maya.id, role="attendee"))
        session.commit()
    finally:
        session.close()

    client = TestClient(app)

    things = client.get("/v1/memory/cards?section=things&q=compass")
    assert things.status_code == 200
    thing_items = things.json()["items"]
    assert len(thing_items) == 1
    thing = thing_items[0]
    assert thing["name"] == "Brass Compass"
    assert thing["provenance"]["kind"] == "entity"
    assert thing["ask_prompt"].startswith("What do you remember about Brass Compass?")
    assert thing["obsidian_path"] == "Things/Brass Compass.md"
    assert thing["timeline"]
    assert thing["source_documents"][0]["title"] == "Attention Architecture Notes"
    assert thing["source_documents"][0]["obsidian_path"] == "Library/Articles/Attention Architecture Notes.md"

    thing_detail = client.get(f"/v1/memory/cards/{thing['id']}")
    assert thing_detail.status_code == 200
    assert thing_detail.json()["all_memories"][0]["text"].startswith("Maya gave")

    concepts = client.get("/v1/memory/cards?section=concepts&q=attention")
    assert concepts.status_code == 200
    assert concepts.json()["items"][0]["name"] == "Attention Architecture"

    events = client.get("/v1/memory/cards?section=events&q=Koyo")
    assert events.status_code == 200
    event_items = events.json()["items"]
    assert any(item["id"].startswith("event:") for item in event_items)
    event_card = next(item for item in event_items if item["id"].startswith("event:"))
    assert event_card["type"] == "event"
    assert event_card["obsidian_path"].startswith("Events/2026/06/2026-06-30 Dinner at Koyo With Maya")
    assert event_card["relationships"][0]["other"] in {"Koyo", "Maya"}

    event_detail = client.get(f"/v1/memory/cards/{event_card['id']}")
    assert event_detail.status_code == 200
    event_body = event_detail.json()
    assert event_body["entries"][0]["raw_text"].startswith("Dinner with Maya")
    assert event_body["timeline"][0]["date"] == "2026-06-30"
