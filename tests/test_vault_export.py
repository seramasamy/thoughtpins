from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest


def _set_vault_path(monkeypatch, config, path: Path) -> None:
    monkeypatch.setattr(config, "VAULT_PATH", path)
    monkeypatch.setattr(type(config), "VAULT_PATH", path)


def test_vault_markdown_helpers_are_obsidian_safe():
    from thoughtpins.vault.markdown import frontmatter_block, markdown_list, parse_frontmatter, safe_filename, wikilink

    assert safe_filename("Maya: <Launch>/[Plan]?*") == "Maya Launch Plan"
    assert safe_filename("CON") == "CON note"
    assert wikilink("People/Maya.md") == "[[People/Maya]]"
    assert wikilink("People/Maya.md", label="Maya P.") == "[[People/Maya|Maya P.]]"
    assert wikilink("Projects/Atlas.md", label="Atlas [v1] | beta") == "[[Projects/Atlas|Atlas (v1) - beta]]"
    assert markdown_list(["line\nbreak"]) == "- line break"

    block = frontmatter_block(
        {
            "id": "note-1",
            "type": "person",
            "title": "Maya",
            "tags": ["thoughtpins", "entity"],
            "related": ["[[Places/Lumen]]"],
        }
    )
    data, _ = parse_frontmatter(block + "# Maya\n")
    assert data["title"] == "Maya"
    assert data["tags"] == ["thoughtpins", "entity"]
    assert data["related"] == ["[[Places/Lumen]]"]


def test_native_obsidian_view_validators_reject_recursive_and_invalid_structures():
    from thoughtpins.vault.bases import validate_base_payload
    from thoughtpins.vault.canvas import load_canvas_bytes, validate_canvas_payload

    recursive: dict[str, object] = {
        "views": [{"type": "table", "name": "Recursive"}],
        "filters": {},
    }
    filters = recursive["filters"]
    assert isinstance(filters, dict)
    filters["and"] = [recursive]
    base_errors = validate_base_payload(recursive)
    assert "Base structure contains a recursive YAML alias" in base_errors

    formula_errors = validate_base_payload(
        {
            "filters": ["formula.missing > 0"],
            "views": [{"type": "table", "name": "Broken"}],
        }
    )
    assert "formula.missing is referenced but not defined" in formula_errors

    with pytest.raises(ValueError, match="non-finite JSON number"):
        load_canvas_bytes(
            b'{"nodes":[{"id":"a","type":"text","text":"A","x":NaN,"y":0,"width":10,"height":10}],"edges":[]}',
        )
    canvas_errors = validate_canvas_payload(
        {
            "nodes": [{"id": "a", "type": "text", "text": "A", "x": 0, "y": 0, "width": 10, "height": 10}],
            "edges": [{"id": "e", "fromNode": "a", "toNode": "missing"}],
        }
    )
    assert "edge e has unknown toNode 'missing'" in canvas_errors


def test_vault_export_full_layout_and_validator(isolated_db, monkeypatch, tmp_path):
    from thoughtpins import library
    from thoughtpins.config import config
    from thoughtpins.db import Entity, EntityMention, Event, EventParticipant, Memory, RawEntry, Relationship
    from thoughtpins.library import ingest_document_text
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text
    from thoughtpins.vault.exporter import VaultExporter
    from thoughtpins.vault.markdown import parse_frontmatter
    from thoughtpins.vault.validator import validate_vault

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("vault-user", session=session)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 5, 23, 14, 30),
            local_date=datetime(2026, 5, 23).date(),
            local_time="14:30",
            source="telegram",
            telegram_chat_id="vault-user",
            raw_text="Today I met Maya P. at Lumen and discussed Project Atlas reliability.",
            content_hash=hash_text("vault entry"),
            processed_status="completed",
            user_importance=5,
            importance_source="user",
        )
        session.add(raw)
        session.flush()
        maya = Entity(user_id=user.id, type="person", canonical_name="Maya", aliases_json=["Maya P."])
        lumen = Entity(user_id=user.id, type="place", canonical_name="Lumen")
        atlas = Entity(user_id=user.id, type="project", canonical_name="Project Atlas")
        compass = Entity(user_id=user.id, type="thing", canonical_name="Brass Compass", aliases_json=["compass token"])
        session.add_all([maya, lumen, atlas, compass])
        session.flush()
        session.add_all(
            [
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=maya.id, surface_text="Maya P."),
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=lumen.id, surface_text="Lumen"),
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=atlas.id, surface_text="Project Atlas"),
                EntityMention(user_id=user.id, raw_entry_id=raw.id, entity_id=compass.id, surface_text="Brass Compass"),
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="observation",
                    subject_entity_id=maya.id,
                    object_entity_id=atlas.id,
                    text="Maya discussed Project Atlas reliability at Lumen.",
                    local_date=raw.local_date,
                    created_at_utc=raw.created_at_utc,
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="object",
                    subject_entity_id=compass.id,
                    text="The brass compass was a launch-day recall marker.",
                    local_date=raw.local_date,
                    created_at_utc=raw.created_at_utc,
                ),
                Relationship(
                    user_id=user.id,
                    source_entity_id=maya.id,
                    target_entity_id=lumen.id,
                    relation_type="met_at",
                    raw_entry_id=raw.id,
                    confidence="observed_by_user",
                ),
            ]
        )
        event = Event(
            user_id=user.id,
            name="Coffee Chat With Maya",
            event_type="meeting",
            local_date=raw.local_date,
            place_entity_id=lumen.id,
            summary="Maya and the user discussed Project Atlas reliability at Lumen.",
            source_raw_entry_id=raw.id,
        )
        session.add(event)
        session.flush()
        session.add(EventParticipant(user_id=user.id, event_id=event.id, entity_id=maya.id, role="attendee"))
        session.commit()

        ingest_document_text(
            session,
            "The Orchard Protocol article says durable AI memory needs provenance and recall diagnostics.",
            user_id=user.id,
            source_type="article",
            title="Orchard Protocol",
            source_url="https://example.com/orchard-protocol",
        )

        exporter = VaultExporter(session, user_id=user.id)
        stats = exporter.export_all(package_zip=True, obsidian_defaults=True)
        root = Path(exporter._vault)
        assert stats["validation_errors"] == 0
        assert stats["entries"] >= 2
        assert stats["people"] == 1
        assert stats["places"] == 1
        assert stats["projects"] == 1
        assert stats["events"] >= 1
        assert stats["things"] == 1
        assert stats["documents"] == 1
        assert stats["bases"] == 4
        assert stats["canvases"] == 1
        assert Path(stats["zip_path"]).exists()
        assert stats["obsidian_defaults"] is True
        assert (root / ".obsidian" / "app.json").exists()

        expected = [
            root / "Vault Home.md",
            root / "Journal" / "2026" / "05" / "2026-05-23.md",
            root / "People" / "Maya.md",
            root / "Places" / "Lumen.md",
            root / "Projects" / "Project Atlas.md",
            root / "Things" / "Brass Compass.md",
            root / "Events" / "2026" / "05" / "2026-05-23 Coffee Chat With Maya.md",
            root / "Library" / "Articles" / "Orchard Protocol.md",
            root / "_Indexes" / "People.md",
            root / "_Indexes" / "Events.md",
            root / "_Indexes" / "Things.md",
            root / "_Views" / "Journal.base",
            root / "_Views" / "Daily Notes.base",
            root / "_Views" / "Memory Cards.base",
            root / "_Views" / "Library.base",
            root / "_Views" / "Memory Map.canvas",
            root / "_System" / "thoughtpins-vault-manifest.json",
        ]
        for path in expected:
            assert path.exists(), path

        person_note = (root / "People" / "Maya.md").read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(person_note)
        assert metadata["type"] == "person"
        assert metadata["aliases"] == ["Maya P."]
        assert "## Card" in body
        assert "| Field | Value |" in body
        assert "[[Places/Lumen" in body

        daily = (root / "Journal" / "2026" / "05" / "2026-05-23.md").read_text(encoding="utf-8")
        assert "[[People/Maya" in daily
        assert "[[Projects/Project Atlas" in daily
        assert "[[Things/Brass Compass" in daily
        assert "(5/5)" in daily

        entry_note = next(
            path for path in (root / "Entries").rglob("*.md") if "Today I met Maya" in path.read_text(encoding="utf-8")
        )
        entry_metadata, entry_body = parse_frontmatter(entry_note.read_text(encoding="utf-8"))
        assert entry_metadata["importance"] == 5
        assert "- Importance: 5/5" in entry_body

        article = (root / "Library" / "Articles" / "Orchard Protocol.md").read_text(encoding="utf-8")
        assert "https://example.com/orchard-protocol" in article
        assert "## Reading Card" in article
        assert "## Extracted Text" in article
        assert "The Orchard Protocol article says" in article

        memory_map = json.loads((root / "_Views" / "Memory Map.canvas").read_text(encoding="utf-8"))
        file_nodes = [node for node in memory_map["nodes"] if node["type"] == "file"]
        assert {node["file"] for node in file_nodes} >= {"People/Maya.md", "Places/Lumen.md"}
        assert any(edge.get("label") == "met at" for edge in memory_map["edges"])

        manifest = json.loads((root / "_System" / "thoughtpins-vault-manifest.json").read_text(encoding="utf-8"))
        assert manifest["version"] == 2
        assert manifest["schema"] == "thoughtpins-vault/2"
        assert "user_id" not in manifest

        validation = validate_vault(root)
        assert validation.ok, validation.as_dict()
    finally:
        session.close()


def test_incremental_vault_export_preserves_user_edits_and_removes_stale_generated_notes(
    isolated_db,
    monkeypatch,
    tmp_path,
):
    from thoughtpins.config import config
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text
    from thoughtpins.vault.exporter import VaultExporter

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("incremental-vault-user", session=session)
        first = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 7, 10, 15, 0),
            local_date=datetime(2026, 7, 10).date(),
            local_time="11:00",
            source="web",
            raw_text="The first generated version of this note.",
            content_hash=hash_text("first generated version"),
            processed_status="completed",
        )
        stale = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 7, 11, 15, 0),
            local_date=datetime(2026, 7, 11).date(),
            local_time="11:00",
            source="web",
            raw_text="This generated note will later be removed.",
            content_hash=hash_text("generated note to remove"),
            processed_status="completed",
        )
        session.add_all([first, stale])
        session.commit()

        exporter = VaultExporter(session, user_id=user.id)
        initial = exporter.export_all(obsidian_defaults=True)
        root = exporter._vault
        entry_path = root / Path(exporter._entry_paths[first.id].as_posix())
        stale_path = root / Path(exporter._entry_paths[stale.id].as_posix())
        stale_daily = root / Path(exporter._daily_paths[stale.local_date].as_posix())
        assert initial["validation_errors"] == 0
        assert (root / "_System" / "thoughtpins-export-state.json").is_file()

        user_edit = entry_path.read_text(encoding="utf-8") + "\nUser-authored annotation that must survive.\n"
        entry_path.write_text(user_edit, encoding="utf-8")
        custom_note = root / "Notes" / "My private scratchpad.md"
        custom_note.parent.mkdir(parents=True, exist_ok=True)
        custom_note.write_text("# My private scratchpad\n\nNever generator-owned.\n", encoding="utf-8")
        first.raw_text = "The database now contains a newer generated version."
        first.content_hash = hash_text(first.raw_text)
        session.delete(stale)
        session.commit()

        preserved = exporter.export_all(incremental=True, conflict_policy="preserve")
        assert preserved["incremental"] is True
        assert preserved["conflicts"] >= 1
        assert entry_path.read_text(encoding="utf-8") == user_edit
        assert custom_note.read_text(encoding="utf-8").endswith("Never generator-owned.\n")
        assert not stale_path.exists()
        assert not stale_daily.exists()

        overwritten = exporter.export_all(incremental=True, conflict_policy="overwrite")
        assert overwritten["conflict_policy"] == "overwrite"
        assert "newer generated version" in entry_path.read_text(encoding="utf-8")
        assert "User-authored annotation" not in entry_path.read_text(encoding="utf-8")
        assert custom_note.is_file()
        assert overwritten["validation_errors"] == 0
    finally:
        session.close()


def test_vault_export_excludes_every_private_derived_artifact(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.config import config
    from thoughtpins.db import DocumentSource, Entity, EntityMention, Event, Memory, RawEntry, Relationship
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text
    from thoughtpins.vault.exporter import VaultExporter

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("private-vault-user", session=session)
        public_text = "I spoke with Rowan about the public Atlas roadmap."
        private_marker = "PRIVATE-ONLY-NIGHTJAR-7429"
        public_entry = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 7, 1, 10, 0),
            local_date=datetime(2026, 7, 1).date(),
            source="web",
            raw_text=public_text,
            content_hash=hash_text(public_text),
            processed_status="completed",
            is_private=False,
        )
        private_entry = RawEntry(
            user_id=user.id,
            created_at_utc=datetime(2026, 7, 2, 10, 0),
            local_date=datetime(2026, 7, 2).date(),
            source="web",
            raw_text=f"Private note {private_marker}",
            content_hash=hash_text(private_marker),
            processed_status="completed",
            is_private=True,
        )
        session.add_all([public_entry, private_entry])
        session.flush()
        rowan = Entity(
            user_id=user.id,
            type="person",
            canonical_name=f"Private Canonical {private_marker}",
            aliases_json=["Private Rowan Alias"],
            attributes_json=[
                {
                    "key": "role",
                    "value": "public collaborator",
                    "source_entry_id": public_entry.id,
                    "confidence": "observed_by_user",
                },
                {
                    "key": "private_code",
                    "value": private_marker,
                    "source_entry_id": private_entry.id,
                    "confidence": "observed_by_user",
                },
                {"key": "legacy_unprovenanced", "value": private_marker},
            ],
        )
        private_person = Entity(
            user_id=user.id,
            type="person",
            canonical_name=f"Hidden Person {private_marker}",
        )
        session.add_all([rowan, private_person])
        session.flush()
        session.add_all(
            [
                EntityMention(
                    user_id=user.id,
                    raw_entry_id=public_entry.id,
                    entity_id=rowan.id,
                    surface_text="Rowan",
                ),
                EntityMention(
                    user_id=user.id,
                    raw_entry_id=private_entry.id,
                    entity_id=private_person.id,
                    surface_text=f"Hidden Person {private_marker}",
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=public_entry.id,
                    memory_type="observation",
                    subject_entity_id=rowan.id,
                    text="Rowan discussed the public Atlas roadmap.",
                    created_at_utc=public_entry.created_at_utc,
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=private_entry.id,
                    memory_type="observation",
                    subject_entity_id=rowan.id,
                    object_entity_id=private_person.id,
                    text=private_marker,
                    created_at_utc=private_entry.created_at_utc,
                ),
                Relationship(
                    user_id=user.id,
                    source_entity_id=rowan.id,
                    target_entity_id=private_person.id,
                    relation_type="private_connection",
                    raw_entry_id=private_entry.id,
                    notes=private_marker,
                ),
                Event(
                    user_id=user.id,
                    name=f"Private Event {private_marker}",
                    event_type="meeting",
                    local_date=private_entry.local_date,
                    summary=private_marker,
                    source_raw_entry_id=private_entry.id,
                ),
                DocumentSource(
                    user_id=user.id,
                    raw_entry_id=private_entry.id,
                    source_type="article",
                    title=f"Private Source {private_marker}",
                    content_hash=hash_text(f"document-{private_marker}"),
                    raw_text=private_marker,
                    status="processed",
                    rights_basis="user_provided",
                ),
            ]
        )
        session.commit()

        exporter = VaultExporter(session, user_id=user.id)
        stats = exporter.export_all(package_zip=True, obsidian_defaults=True)
        root = Path(exporter._vault)
        all_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace") for path in sorted(root.rglob("*")) if path.is_file()
        )
        assert "public Atlas roadmap" in all_text
        assert "public collaborator" in all_text
        assert private_marker not in all_text
        assert "Private Rowan Alias" not in all_text
        assert "private_connection" not in all_text
        assert stats["validation_errors"] == 0

        with zipfile.ZipFile(stats["zip_path"]) as package:
            assert private_marker not in "\n".join(package.namelist())
            zipped_text = "\n".join(package.read(name).decode("utf-8", errors="replace") for name in package.namelist())
        assert private_marker not in zipped_text
    finally:
        session.close()


def test_vault_validator_catches_broken_links_and_secrets(tmp_path):
    from thoughtpins.vault.markdown import frontmatter_block
    from thoughtpins.vault.validator import validate_vault

    vault = tmp_path / "bad-vault"
    vault.mkdir()
    note = vault / "Broken.md"
    note.write_text(
        frontmatter_block(
            {
                "id": "broken",
                "type": "entry",
                "title": "Broken",
                "created": "2026-05-23",
                "updated": "2026-05-23",
                "source": "test",
                "tags": ["thoughtpins"],
                "aliases": [],
                "thoughtpins_id": "broken",
                "related": ["[[People/Missing]]"],
            }
        )
        + "# Broken\n\nThis links to [[People/Missing]] and leaks "
        + "sk-"
        + "testtokenwithwaytoomanycharacters12345.\n",
        encoding="utf-8",
    )
    result = validate_vault(vault)
    assert not result.ok
    messages = "\n".join(finding.message for finding in result.errors)
    assert "broken wikilink" in messages
    assert "possible secret" in messages


def test_vault_export_api_route_returns_validation_and_zip(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    _set_vault_path(monkeypatch, config, tmp_path / "vault")
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        session.add(
            RawEntry(
                user_id=user.id,
                created_at_utc=datetime(2026, 5, 24, 9, 0),
                local_date=datetime(2026, 5, 24).date(),
                local_time="09:00",
                source="api",
                raw_text="Today I checked that vault export works through the API.",
                content_hash=hash_text("api vault export"),
                processed_status="completed",
            )
        )
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    response = client.post("/v1/export/vault?zip=true&obsidian_defaults=true")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "obsidian_compatible_vault"
    assert body["validation"]["ok"] is True
    assert body["stats"]["obsidian_defaults"] is True
    assert "zip_path" not in body["stats"]
    assert "vault_path" not in body


def test_vault_validator_hardens_obsidian_edge_cases(tmp_path):
    from thoughtpins.vault.markdown import fenced_text, frontmatter_block
    from thoughtpins.vault.validator import validate_vault

    vault = tmp_path / "edge-vault"
    vault.mkdir()

    def write_note(rel: str, note_type: str, title: str, body: str, related: list[str] | None = None) -> None:
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            frontmatter_block(
                {
                    "id": rel.lower().replace("/", "-"),
                    "type": note_type,
                    "title": title,
                    "created": "2026-06-30T00:00:00+00:00",
                    "updated": "2026-06-30T00:00:00+00:00",
                    "source": "test",
                    "tags": ["thoughtpins", "test"],
                    "aliases": [],
                    "thoughtpins_id": rel.lower().replace("/", "-"),
                    "related": related or [],
                }
            )
            + body,
            encoding="utf-8",
        )

    index_links = [
        "[[_Indexes/Journal]]",
        "[[_Indexes/Entries]]",
        "[[_Indexes/People]]",
        "[[_Indexes/Places]]",
        "[[_Indexes/Organizations]]",
        "[[_Indexes/Projects]]",
        "[[_Indexes/Events]]",
        "[[_Indexes/Things]]",
        "[[_Indexes/Concepts]]",
        "[[_Indexes/Library]]",
    ]
    write_note(
        "Vault Home.md",
        "home",
        "Vault Home",
        "# Vault Home\n\n## Start Here\n- [[_Indexes/Journal]]\n\n## Current Counts\n- Entries: 1\n\n## Open In Obsidian\n- Open this folder as a vault.\n\n## System Boundary\nInternal systems stay separate.\n",
        index_links,
    )
    for name in [
        "Journal",
        "Entries",
        "People",
        "Places",
        "Organizations",
        "Projects",
        "Events",
        "Things",
        "Concepts",
        "Library",
    ]:
        write_note(f"_Indexes/{name}.md", "index", name, f"# {name}\n\n- No notes exported yet.\n")
    system = vault / "_System"
    system.mkdir()
    (system / "thoughtpins-vault-manifest.json").write_text(
        json.dumps({"app": "Thought Pins", "format": "obsidian-compatible-vault", "version": 1}),
        encoding="utf-8",
    )
    write_note(
        "Journal/2026/06/2026-06-30.md",
        "daily_journal",
        "2026-06-30",
        "# 2026-06-30\n\n## Entries\n- [[Entries/2026/06/30/Entry]]\n\n## Mentioned\n- None recorded.\n",
        ["[[Entries/2026/06/30/Entry]]"],
    )
    write_note(
        "Entries/2026/06/30/Entry.md",
        "entry",
        "Entry",
        "# Entry\n\n## Context\n- Source: test\n\n## Mentioned\n- None recorded.\n\n## Memories\n- No extracted memories recorded.\n\n## Original Text\n"
        + fenced_text("This source text mentions [[People/Fenced Missing]] but it is deliberately fenced."),
    )
    obsidian = vault / ".obsidian"
    obsidian.mkdir()
    (obsidian / "app.json").write_text("{not valid json", encoding="utf-8")

    result = validate_vault(vault)
    assert not result.ok
    messages = "\n".join(finding.message for finding in result.errors)
    assert ".obsidian JSON is invalid" in messages
    assert "entry note does not link its daily note" in messages
    assert "Fenced Missing" not in messages


def test_vault_stress_harness_offline_cleans_temp(tmp_path):
    temp_root = tmp_path / "stress-temp"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/stress_vault_obsidian.py",
            "--offline-fixture",
            "--max-source-chars",
            "8000",
            "--temp-root",
            str(temp_root),
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["cleaned"] is True
    assert payload["live_downloads"] is False
    assert len(payload["corpus"]) == 7
    assert payload["export_stats"]["documents"] == 7
    assert payload["validation"]["ok"] is True
    assert payload["isolated_check"]["ok"] is True
    assert not temp_root.exists()
