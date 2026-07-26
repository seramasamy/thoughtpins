from __future__ import annotations

from datetime import date


def test_extraction_models_normalize_to_memory_ontology():
    from thoughtpins.llm import ExtractedEntity, ExtractedRelationship

    entity = ExtractedEntity(surface_name="OpenAI", type="company")
    relation = ExtractedRelationship(source="Thought Pins", relation_type="runs_on", target="PostgreSQL")

    assert entity.type == "organization"
    assert relation.relation_type == "uses_technology"


def test_ontology_constraints_filter_invalid_edges(isolated_db):
    from thoughtpins.db import RawEntry, Relationship, User
    from thoughtpins.ingestion.pipeline import _store_extraction
    from thoughtpins.llm import ExtractedEntity, ExtractedRelationship, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = User(email="ontology@example.local", display_name="Ontology Test")
        session.add(user)
        session.flush()
        raw_entry = RawEntry(
            user_id=user.id,
            local_date=date(2026, 5, 30),
            raw_text="I work on Thought Pins and it uses PostgreSQL. Alice uses Bob.",
            content_hash=hash_text("ontology test"),
            processed_status="processing",
        )
        session.add(raw_entry)
        session.flush()

        extraction = ExtractionResult(
            entry_summary="Ontology test",
            entities=[
                ExtractedEntity(surface_name="User", canonical_guess="User", type="person"),
                ExtractedEntity(surface_name="Thought Pins", canonical_guess="Thought Pins", type="project"),
                ExtractedEntity(surface_name="PostgreSQL", canonical_guess="PostgreSQL", type="database"),
                ExtractedEntity(surface_name="Alice", canonical_guess="Alice", type="person"),
                ExtractedEntity(surface_name="Bob", canonical_guess="Bob", type="person"),
            ],
            relationships=[
                ExtractedRelationship(source="User", relation_type="works_on", target="Thought Pins"),
                ExtractedRelationship(source="Thought Pins", relation_type="runs_on", target="PostgreSQL"),
                ExtractedRelationship(source="Alice", relation_type="uses_technology", target="Bob"),
            ],
        )

        stats = _store_extraction(session, raw_entry, extraction, date(2026, 5, 30), raw_text=raw_entry.raw_text)
        session.flush()
        relation_types = [rel.relation_type for rel in session.query(Relationship).all()]

        assert stats["relationships"] == 2
        assert relation_types == ["works_on", "uses_technology"]
    finally:
        session.close()


def test_ontology_allows_personal_memory_graph_edges_from_live_notes():
    from thoughtpins.memory.ontology import relationship_allowed

    assert relationship_allowed("discussed", "person", "technology").allowed
    assert relationship_allowed("created", "person", "topic").allowed
    assert relationship_allowed("created", "person", "concept").allowed
    assert not relationship_allowed("located_at", "place", "place").allowed
