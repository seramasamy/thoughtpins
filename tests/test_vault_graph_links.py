"""The vault has to be one graph, not a pile of notes.

A saved article that names the same people and ideas as a journal entry should
land on the same nodes in Obsidian's graph view, and a remembered sentence should
be findable as a quote rather than buried in a list of memories.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from thoughtpins.utils import hash_text


def _set_vault_path(monkeypatch, config, path: Path) -> None:
    monkeypatch.setattr(config, "VAULT_PATH", path)
    monkeypatch.setattr(type(config), "VAULT_PATH", path)


def _seed(session, user_id: str):
    """A journal entry naming two people, one of them quoted, plus a topic."""
    from thoughtpins.db import Entity, EntityMention, Memory, RawEntry

    raw = RawEntry(
        user_id=user_id,
        created_at_utc=datetime(2026, 5, 23, 14, 30),
        local_date=datetime(2026, 5, 23).date(),
        local_time="14:30",
        source="web",
        raw_text="Maya told Femi she is leaving in March, and we talked about Zettelkasten.",
        content_hash=hash_text("graph link entry"),
        processed_status="completed",
    )
    session.add(raw)
    session.flush()
    maya = Entity(user_id=user_id, type="person", canonical_name="Maya Okonkwo")
    femi = Entity(user_id=user_id, type="person", canonical_name="Femi Okonkwo")
    zettel = Entity(user_id=user_id, type="topic", canonical_name="Zettelkasten")
    session.add_all([maya, femi, zettel])
    session.flush()
    session.add_all(
        [
            EntityMention(user_id=user_id, raw_entry_id=raw.id, entity_id=maya.id, surface_text="Maya Okonkwo"),
            EntityMention(user_id=user_id, raw_entry_id=raw.id, entity_id=femi.id, surface_text="Femi Okonkwo"),
            EntityMention(user_id=user_id, raw_entry_id=raw.id, entity_id=zettel.id, surface_text="Zettelkasten"),
            Memory(
                user_id=user_id,
                raw_entry_id=raw.id,
                memory_type="quote",
                subject_entity_id=maya.id,
                predicate="said",
                text='Maya said: "I am finally leaving in March"',
                structured_json={
                    "attributed_to": "Maya Okonkwo",
                    "people_involved": ["Maya Okonkwo", "Femi Okonkwo"],
                },
                local_date=raw.local_date,
                created_at_utc=raw.created_at_utc,
            ),
            Memory(
                user_id=user_id,
                raw_entry_id=raw.id,
                memory_type="observation",
                subject_entity_id=maya.id,
                text="Maya has been reading about note-taking systems.",
                local_date=raw.local_date,
                created_at_utc=raw.created_at_utc,
            ),
        ]
    )
    session.commit()
    return raw


def _add_article(session, user_id: str, raw_entry_id: str):
    """A saved article whose reading analysis names one known and one unknown topic."""
    from thoughtpins.db import DocumentSource

    document = DocumentSource(
        user_id=user_id,
        raw_entry_id=raw_entry_id,
        source_type="article",
        title="Notes That Point At Each Other",
        author="Ada Whitfield",
        source_url="https://example.com/notes",
        source_domain="example.com",
        rights_basis="user_provided",
        content_hash=hash_text("article graph link"),
        raw_text="A short article about linking notes together.",
        status="processed",
        fetch_status="processed",
        created_at_utc=datetime(2026, 5, 23, 15, 0),
        metadata_json={
            "reading_analysis": {
                "topics": ["Zettelkasten", "a topic with no note"],
                "key_concepts": ["Maya Okonkwo", "Some Unmatched Concept"],
            }
        },
    )
    session.add(document)
    session.commit()
    return document


def _export(session, user_id: str, tmp_path: Path):
    from thoughtpins.vault.exporter import VaultExporter

    exporter = VaultExporter(session, user_id=user_id, vault_path=tmp_path / "vault")
    exporter.export_all(validate=True)
    return exporter, Path(exporter._vault)


def test_article_topics_link_to_notes_that_exist_and_stay_text_when_they_do_not(
    isolated_db, monkeypatch, tmp_path
):
    from thoughtpins.config import config
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw = _seed(session, user.id)
        _add_article(session, user.id, raw.id)
        exporter, root = _export(session, user.id, tmp_path)

        note = (root / "Library/Articles/Notes That Point At Each Other.md").read_text(encoding="utf-8")
        assert "[[Concepts/Zettelkasten|Zettelkasten]]" in note
        assert "[[People/Maya Okonkwo|Maya Okonkwo]]" in note
        # Topics with no matching note stay plain, so the vault never links to nothing.
        assert "- a topic with no note" in note
        assert "- Some Unmatched Concept" in note
        assert exporter.validation_result is not None and exporter.validation_result.ok
    finally:
        session.close()


def test_article_joins_the_graph_through_its_related_links(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.config import config
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.vault.markdown import parse_frontmatter

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        raw = _seed(session, user.id)
        _add_article(session, user.id, raw.id)
        _, root = _export(session, user.id, tmp_path)

        metadata, _ = parse_frontmatter(
            (root / "Library/Articles/Notes That Point At Each Other.md").read_text(encoding="utf-8")
        )
        related = " ".join(metadata.get("related") or [])
        # Obsidian's graph reads frontmatter links too, so the subject links have
        # to be there and not only in the body.
        assert "Concepts/Zettelkasten" in related
        assert "People/Maya Okonkwo" in related
    finally:
        session.close()


def test_quotes_get_their_own_section_and_link_the_people_they_name(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.config import config
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        _seed(session, user.id)
        _, root = _export(session, user.id, tmp_path)

        note = (root / "People/Maya Okonkwo.md").read_text(encoding="utf-8")
        quotes = note.split("## Quotes", 1)[1].split("\n## ", 1)[0]
        assert "I am finally leaving in March" in quotes
        assert "[[People/Femi Okonkwo|Femi Okonkwo]]" in quotes
        # The speaker is not listed as someone the quote mentions.
        assert "[[People/Maya Okonkwo" not in quotes

        # A quote belongs in the quotes section, not repeated among memories.
        memories = note.split("## Recent Memories", 1)[1].split("\n## ", 1)[0]
        assert "I am finally leaving in March" not in memories
        assert "reading about note-taking systems" in memories
    finally:
        session.close()


def test_entity_note_without_quotes_says_so(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.config import config
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        _seed(session, user.id)
        _, root = _export(session, user.id, tmp_path)

        note = (root / "People/Femi Okonkwo.md").read_text(encoding="utf-8")
        assert "## Quotes\n- No quotes recorded yet." in note
    finally:
        session.close()


def test_validator_requires_the_quotes_section_on_entity_notes(tmp_path):
    from thoughtpins.vault.validator import TYPE_REQUIRED_SECTIONS

    for note_type in ("person", "place", "organization", "project", "thing", "concept"):
        assert "## Quotes" in TYPE_REQUIRED_SECTIONS[note_type]


def test_saved_sources_are_extracted_into_the_graph_by_default():
    """Off by default left every saved article an island in the vault."""
    from thoughtpins.config import Config

    assert Config.LIBRARY_EXTRACT_GRAPH is True


def test_key_concepts_do_not_run_across_sentences_or_grab_sentence_starts():
    from thoughtpins.reading_analysis import extract_key_concepts

    concepts = extract_key_concepts(
        "The Case for Atomic Notes",
        "Atomic notes hold one idea each. Modern tools like Obsidian rebuild this. "
        "Sonke Ahrens argues the value comes from the writing.",
    )
    joined = " | ".join(concepts)
    assert "Obsidian" in concepts
    assert "Sonke Ahrens" in concepts
    # A phrase must not run past a full stop, and a word is not a name just
    # because it opens a sentence.
    assert "." not in joined.replace("Ahrens", "")
    assert "Modern" not in concepts
    assert "The Case" not in concepts
