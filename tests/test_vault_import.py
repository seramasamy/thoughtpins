from __future__ import annotations

import base64
import hashlib
import io
import json
import stat
import zipfile
from datetime import datetime
from pathlib import Path

import pytest


def _zip(files: dict[str, str | bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as package:
        for name, content in files.items():
            package.writestr(name, content.encode("utf-8") if isinstance(content, str) else content)
    return stream.getvalue()


def _frontmatter(**values: object) -> str:
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines + ["---", ""])


def test_obsidian_frontmatter_preserves_typed_properties_and_nested_links():
    from thoughtpins.vault.frontmatter import extract_wikilinks, parse_obsidian_frontmatter

    markdown = """---
title: "Coffee: follow-up"
importance: 4
private: false
date: 2026-07-14
people:
  - "[[People/Maya|Maya]]"
context:
  place: "[[Places/Atlas Cafe]]"
  topics:
    - memory systems
---
# Coffee follow-up

The body links to [[Projects/Atlas]].
"""
    metadata, body = parse_obsidian_frontmatter(markdown)
    assert metadata["title"] == "Coffee: follow-up"
    assert metadata["importance"] == 4
    assert metadata["private"] is False
    assert metadata["date"] == "2026-07-14"
    assert metadata["context"]["topics"] == ["memory systems"]
    assert extract_wikilinks(metadata, body) == [
        "People/Maya|Maya",
        "Places/Atlas Cafe",
        "Projects/Atlas",
    ]

    recursive = "---\nloop: &loop [*loop]\n---\n# Recursive\n"
    with pytest.raises(ValueError, match="recursive alias"):
        parse_obsidian_frontmatter(recursive)


def test_imports_arbitrary_obsidian_vault_with_safe_memory_boundary(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import DocumentSource, IngestionJob
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.vault.importer import import_obsidian_vault

    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    archive = _zip(
        {
            "My Vault/.obsidian/app.json": "{}",
            "My Vault/Journal/2024-01-02.md": (
                _frontmatter(title="A winter Tuesday", date="2024-01-02", tags=["journal", "personal"])
                + "# A winter Tuesday\n\nI met Nia at the green cafe and ordered cardamom tea."
            ),
            "My Vault/Research/Bridge Note.md": (
                _frontmatter(title="Bridge Note", tags=["research"])
                + "# Bridge Note\n\nProject Atlas uses a provenance ledger. See [[Architecture]]."
            ),
            "My Vault/Attachments/receipt.png": b"not-a-real-image",
        }
    )

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("obsidian-import-user", session=session)
        result = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="My Vault.zip",
            archive=archive,
            enqueue_jobs=False,
        )
        assert result.status == "completed"
        assert result.thoughtpins_export is False
        assert result.notes_discovered == 2
        assert result.journal_notes == 1
        assert result.library_notes == 1
        assert result.journal_jobs_queued == 1
        assert result.library_documents_imported == 1
        assert result.attachments_skipped == 1

        job = session.query(IngestionJob).filter(IngestionJob.user_id == user.id).one()
        assert job.status == "pending"
        assert job.metadata_json["force_journal"] is True
        assert job.metadata_json["vault_path"] == "Journal/2024-01-02.md"
        assert job.metadata_json["occurred_at_utc"].startswith("2024-01-02")

        document = session.query(DocumentSource).filter(DocumentSource.user_id == user.id).one()
        assert document.title == "Bridge Note"
        assert document.source_type == "obsidian_note"
        assert "Project Atlas uses a provenance ledger" in document.raw_text
        assert document.metadata_json["obsidian_import"]["wikilinks"] == ["Architecture"]

        repeated = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="My Vault.zip",
            archive=archive,
            enqueue_jobs=False,
        )
        assert repeated.imported == 0
        assert repeated.duplicates == 2
        assert session.query(IngestionJob).filter(IngestionJob.user_id == user.id).count() == 1
        assert session.query(DocumentSource).filter(DocumentSource.user_id == user.id).count() == 1
    finally:
        session.close()


def test_vault_import_previews_conflicts_and_appends_explicit_revisions(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import DocumentSource
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.vault.importer import import_obsidian_vault

    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    first = _zip({"Notes/Plan.md": "# Plan\n\nStart with the smallest useful experiment."})
    changed = _zip({"Notes/Plan.md": "# Plan\n\nStart with the smallest reversible experiment."})

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("obsidian-revision-user", session=session)
        initial = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="notes.zip",
            archive=first,
            enqueue_jobs=False,
        )
        assert initial.new_notes == 1
        assert initial.imported == 1

        preview = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="notes.zip",
            archive=changed,
            dry_run=True,
            conflict_policy="skip",
            enqueue_jobs=False,
        )
        assert preview.changed_notes == 1
        assert preview.conflicts == 1
        assert preview.imported == 0
        assert preview.preview_items[0].action == "skip_conflict"

        appended = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="notes.zip",
            archive=changed,
            conflict_policy="append",
            enqueue_jobs=False,
        )
        assert appended.changed_notes == 1
        assert appended.library_documents_imported == 1
        assert appended.preview_items[0].action == "append_revision"
        documents = session.query(DocumentSource).filter(DocumentSource.user_id == user.id).all()
        assert len(documents) == 2
        revised = next(document for document in documents if "reversible" in document.raw_text)
        assert revised.metadata_json["obsidian_import"]["revision_state"] == "changed"

        repeated = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="notes.zip",
            archive=changed,
            conflict_policy="append",
            enqueue_jobs=False,
        )
        assert repeated.unchanged_notes == 1
        assert repeated.duplicates == 1
        assert repeated.imported == 0
    finally:
        session.close()


def test_imports_user_canvas_as_recallable_library_source_and_skips_bases(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import DocumentSource
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.vault.importer import import_obsidian_vault

    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    canvas = {
        "nodes": [
            {
                "id": "idea-node",
                "type": "text",
                "text": "Project Atlas should keep provenance beside every recalled claim.",
                "x": 0,
                "y": 0,
                "width": 320,
                "height": 140,
            },
            {
                "id": "note-node",
                "type": "file",
                "file": "Notes/Architecture.md",
                "x": 420,
                "y": 0,
                "width": 320,
                "height": 140,
            },
            {
                "id": "link-node",
                "type": "link",
                "url": "https://example.com/provenance",
                "x": 840,
                "y": 0,
                "width": 320,
                "height": 140,
            },
        ],
        "edges": [
            {
                "id": "edge-1",
                "fromNode": "idea-node",
                "toNode": "note-node",
                "label": "explained by",
            },
        ],
    }
    archive = _zip(
        {
            "Research Vault/.obsidian/app.json": "{}",
            "Research Vault/Notes/Architecture.md": "# Architecture\n\nA note about durable recall.",
            "Research Vault/Boards/Atlas.canvas": json.dumps(canvas),
            "Research Vault/_Views/Sources.base": "views:\n  - type: table\n    name: Sources\n",
        }
    )

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("canvas-import-user", session=session)
        result = import_obsidian_vault(
            session,
            user_id=user.id,
            filename="Research Vault.zip",
            archive=archive,
            enqueue_jobs=False,
        )
        assert result.status == "completed"
        assert result.canvases_discovered == 1
        assert result.canvas_documents_imported == 1
        assert result.structural_files_skipped == 1
        assert result.attachments_skipped == 0
        assert result.notes_discovered == 2
        assert result.library_documents_imported == 2

        canvas_document = (
            session.query(DocumentSource)
            .filter(DocumentSource.user_id == user.id, DocumentSource.source_type == "obsidian_canvas")
            .one()
        )
        assert canvas_document.title == "Atlas"
        assert "Project Atlas should keep provenance" in canvas_document.raw_text
        assert "explained by" in canvas_document.raw_text
        assert "Notes/Architecture" in canvas_document.raw_text
    finally:
        session.close()


def test_thoughtpins_vault_export_import_round_trip_preserves_sources_and_dates(
    isolated_db,
    monkeypatch,
    tmp_path,
):
    from thoughtpins import library
    from thoughtpins.config import config
    from thoughtpins.db import DocumentSource, IngestionJob, RawEntry
    from thoughtpins.jobs import run_ingestion_job
    from thoughtpins.library import ingest_document_text
    from thoughtpins.llm import ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text
    from thoughtpins.vault.exporter import VaultExporter
    from thoughtpins.vault.importer import import_obsidian_vault

    monkeypatch.setattr(config, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(type(config), "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(),
    )

    session = get_session()
    try:
        source_user = get_or_create_user_for_telegram("vault-source-user", session=session)
        original_text = "I met Nia at the green cafe and ordered cardamom tea before the Atlas review."
        session.add(
            RawEntry(
                user_id=source_user.id,
                created_at_utc=datetime(2023, 11, 5, 18, 45),
                local_date=datetime(2023, 11, 5).date(),
                local_time="13:45",
                source="web",
                raw_text=original_text,
                content_hash=hash_text(original_text),
                processed_status="completed",
                user_importance=4,
                importance_source="user",
            )
        )
        session.commit()
        source_document = ingest_document_text(
            session,
            "A provenance ledger records where every recalled claim originated.",
            user_id=source_user.id,
            source_type="article",
            title="Provenance Ledger",
            source_url="https://example.com/provenance-ledger",
            defer_vector_index=True,
        )

        exporter = VaultExporter(session, user_id=source_user.id, vault_path=tmp_path / "export")
        stats = exporter.export_all(package_zip=True, obsidian_defaults=True)
        archive = Path(stats["zip_path"]).read_bytes()

        target_user = get_or_create_user_for_telegram("vault-target-user", session=session)
        result = import_obsidian_vault(
            session,
            user_id=target_user.id,
            filename="thought-pins-vault.zip",
            archive=archive,
            enqueue_jobs=False,
        )
        assert result.thoughtpins_export is True
        assert result.format == "thoughtpins_obsidian_vault"
        assert result.journal_notes == 1
        assert result.library_notes == 1
        assert result.library_documents_imported == 1
        assert result.journal_jobs_queued == 1

        target_document = session.query(DocumentSource).filter(DocumentSource.user_id == target_user.id).one()
        assert target_document.raw_text == "A provenance ledger records where every recalled claim originated."
        assert target_document.source_url == "https://example.com/provenance-ledger"
        assert target_document.id != source_document.document_id

        job = session.query(IngestionJob).filter(IngestionJob.user_id == target_user.id).one()
        job_id = job.id
        target_user_id = target_user.id
    finally:
        session.close()

    run_ingestion_job(job_id, target_user_id)

    verification = get_session()
    try:
        job = verification.query(IngestionJob).filter(IngestionJob.id == job_id).one()
        imported_entry = verification.query(RawEntry).filter(RawEntry.id == job.entry_id).one()
        assert job.status == "completed"
        assert imported_entry.raw_text == original_text
        assert imported_entry.source == "obsidian_import"
        assert imported_entry.local_date.isoformat() == "2023-11-05"
        assert imported_entry.user_importance == 4
    finally:
        verification.close()


def test_edited_obsidian_vault_round_trip_preserves_user_content_and_skips_views(
    isolated_db,
    monkeypatch,
    tmp_path,
):
    from thoughtpins import library
    from thoughtpins.db import DocumentSource, IngestionJob, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text
    from thoughtpins.vault.exporter import VaultExporter
    from thoughtpins.vault.importer import import_obsidian_vault

    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    session = get_session()
    try:
        source_user = get_or_create_user_for_telegram("edited-vault-source", session=session)
        original = "I planned a quiet walk after the architecture review."
        source_entry = RawEntry(
            user_id=source_user.id,
            created_at_utc=datetime(2026, 7, 12, 18, 0),
            local_date=datetime(2026, 7, 12).date(),
            local_time="14:00",
            source="web",
            raw_text=original,
            content_hash=hash_text(original),
            processed_status="completed",
            user_importance=3,
            importance_source="user",
        )
        session.add(source_entry)
        session.commit()

        exporter = VaultExporter(session, user_id=source_user.id, vault_path=tmp_path / "export")
        stats = exporter.export_all(package_zip=True, obsidian_defaults=True)
        source_archive = Path(stats["zip_path"])
        edited_stream = io.BytesIO()
        with (
            zipfile.ZipFile(source_archive) as source_zip,
            zipfile.ZipFile(
                edited_stream,
                "w",
                zipfile.ZIP_DEFLATED,
            ) as edited_zip,
        ):
            for info in source_zip.infolist():
                content = source_zip.read(info.filename)
                if info.filename.startswith("Entries/") and info.filename.endswith(".md"):
                    text = content.decode("utf-8")
                    text = text.replace("importance: 3", "importance: 5")
                    text = text.replace(original, "I took the quiet walk and decided to simplify the architecture.")
                    content = text.encode("utf-8")
                edited_zip.writestr(info, content)
            edited_zip.writestr(
                "Notes/Field Notes.md",
                _frontmatter(title="Field Notes", tags=["research", "systems"])
                + "# Field Notes\n\nThe key bridge is [[Architecture]] and a reversible rollout.",
            )
            edited_zip.writestr(
                "Boards/Review.canvas",
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "decision",
                                "type": "text",
                                "text": "Prefer reversible architecture decisions.",
                                "x": 0,
                                "y": 0,
                                "width": 320,
                                "height": 120,
                            }
                        ],
                        "edges": [],
                    }
                ),
            )
            edited_zip.writestr("_Views/User Review.base", "views:\n  - type: table\n    name: User Review\n")

        target_user = get_or_create_user_for_telegram("edited-vault-target", session=session)
        result = import_obsidian_vault(
            session,
            user_id=target_user.id,
            filename="edited-thought-pins-vault.zip",
            archive=edited_stream.getvalue(),
            enqueue_jobs=False,
        )
        assert result.thoughtpins_export is True
        assert result.journal_jobs_queued == 1
        assert result.library_documents_imported == 2
        assert result.canvas_documents_imported == 1
        assert result.structural_files_skipped >= 5

        job = session.query(IngestionJob).filter(IngestionJob.user_id == target_user.id).one()
        assert "decided to simplify the architecture" in job.raw_text
        assert job.metadata_json["user_importance"] == 5
        documents = session.query(DocumentSource).filter(DocumentSource.user_id == target_user.id).all()
        field_note = next(document for document in documents if document.title == "Field Notes")
        assert field_note.metadata_json["obsidian_import"]["wikilinks"] == ["Architecture"]
        canvas = next(document for document in documents if document.source_type == "obsidian_canvas")
        assert "reversible architecture decisions" in canvas.raw_text
    finally:
        session.close()


def test_vault_import_rejects_traversal_symlinks_and_bomb_ratios(isolated_db):
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.vault.importer import import_obsidian_vault

    traversal = _zip({"../escape.md": "# Escape"})
    symlink_stream = io.BytesIO()
    with zipfile.ZipFile(symlink_stream, "w") as package:
        link = zipfile.ZipInfo("linked.md")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(link, "target.md")
    bomb = _zip({"repeated.md": "A" * (1024 * 1024)})

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("vault-security-user", session=session)
        for name, archive, expected in [
            ("traversal.zip", traversal, "unsafe path"),
            ("symlink.zip", symlink_stream.getvalue(), "symbolic links"),
            ("bomb.zip", bomb, "compression ratio"),
        ]:
            with pytest.raises(ValueError, match=expected):
                import_obsidian_vault(
                    session,
                    user_id=user.id,
                    filename=name,
                    archive=archive,
                    enqueue_jobs=False,
                )
    finally:
        session.close()


def test_obsidian_import_and_download_api_contract(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import library
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(config, "VAULT_PATH", tmp_path / "api-vault")
    monkeypatch.setattr(type(config), "VAULT_PATH", tmp_path / "api-vault")
    monkeypatch.setattr(config, "MAX_REQUEST_BODY_BYTES", 100)
    monkeypatch.setattr(type(config), "MAX_REQUEST_BODY_BYTES", 100)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr("thoughtpins.vault.importer.enqueue_ingestion_job", lambda job_id, user_id=None: None)

    client = TestClient(app)
    archive = _zip({"Notes/Reference.md": "# Reference\n\nA durable fact with [[Provenance]]."})
    response = client.post(
        "/v1/import/obsidian",
        json={
            "filename": "notes.zip",
            "content_base64": base64.b64encode(archive).decode("ascii"),
            "mode": "auto",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "obsidian_vault"
    assert body["notes_discovered"] == 1
    assert body["library_documents_imported"] == 1
    assert body["journal_jobs_queued"] == 0
    assert body["canvases_discovered"] == 0
    assert body["canvas_documents_imported"] == 0
    assert body["structural_files_skipped"] == 0

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        text = "Today I verified that a downloadable vault is available to the account owner."
        session.add(
            RawEntry(
                user_id=user.id,
                created_at_utc=datetime(2026, 7, 10, 15, 0),
                local_date=datetime(2026, 7, 10).date(),
                local_time="11:00",
                source="web",
                raw_text=text,
                content_hash=hash_text(text),
                processed_status="completed",
            )
        )
        session.commit()
    finally:
        session.close()

    download = client.get("/v1/export/vault/download")
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "application/zip"
    assert "attachment" in download.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as package:
        names = package.namelist()
        assert "Vault Home.md" in names
        manifest = json.loads(package.read("_System/thoughtpins-vault-manifest.json"))
        assert manifest["app"] == "Thought Pins"


def test_resumable_vault_upload_preview_apply_retry_and_cancel(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import library
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.vault import transfers

    import_root = tmp_path / "vault-imports"
    monkeypatch.setattr(config, "VAULT_IMPORT_PATH", import_root)
    monkeypatch.setattr(type(config), "VAULT_IMPORT_PATH", import_root)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(transfers, "enqueue_vault_import_session", lambda transfer_id, user_id=None: None)

    archive = _zip(
        {
            "My Vault/.obsidian/app.json": "{}",
            "My Vault/Notes/Reference.md": "# Reference\n\nA durable fact connected to [[Provenance]].",
        }
    )
    archive_sha = hashlib.sha256(archive).hexdigest()
    client = TestClient(app)
    created = client.post(
        "/v1/import/obsidian/uploads",
        json={
            "filename": "My Vault.zip",
            "expected_bytes": len(archive),
            "archive_sha256": archive_sha,
            "mode": "auto",
            "conflict_policy": "skip",
        },
    )
    assert created.status_code == 201, created.text
    transfer_id = created.json()["id"]
    split = max(1, len(archive) // 2)
    chunks = [archive[:split], archive[split:]]

    offset = 0
    first_payload = {
        "offset": 0,
        "content_base64": base64.b64encode(chunks[0]).decode("ascii"),
        "chunk_sha256": hashlib.sha256(chunks[0]).hexdigest(),
    }
    first = client.put(f"/v1/import/obsidian/uploads/{transfer_id}/chunks", json=first_payload)
    assert first.status_code == 200, first.text
    assert first.json()["received_bytes"] == len(chunks[0])

    retried = client.put(f"/v1/import/obsidian/uploads/{transfer_id}/chunks", json=first_payload)
    assert retried.status_code == 200, retried.text
    assert retried.json()["received_bytes"] == len(chunks[0])
    gap = client.put(
        f"/v1/import/obsidian/uploads/{transfer_id}/chunks",
        json={
            "offset": offset + len(chunks[0]) + 1,
            "content_base64": base64.b64encode(chunks[1][:-1]).decode("ascii"),
            "chunk_sha256": hashlib.sha256(chunks[1][:-1]).hexdigest(),
        },
    )
    assert gap.status_code == 409

    offset += len(chunks[0])
    second = client.put(
        f"/v1/import/obsidian/uploads/{transfer_id}/chunks",
        json={
            "offset": offset,
            "content_base64": base64.b64encode(chunks[1]).decode("ascii"),
            "chunk_sha256": hashlib.sha256(chunks[1]).hexdigest(),
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "upload_ready"
    assert second.json()["archive_sha256"] == archive_sha

    preview = client.post(f"/v1/import/obsidian/uploads/{transfer_id}/preview", json={})
    assert preview.status_code == 202, preview.text
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        user_id = user.id
    finally:
        session.close()
    monkeypatch.setattr(config, "VAULT_IMPORT_PATH", tmp_path / "separate-worker")
    monkeypatch.setattr(type(config), "VAULT_IMPORT_PATH", tmp_path / "separate-worker")
    transfers.run_vault_import_session(transfer_id, user_id)

    ready = client.get(f"/v1/import/obsidian/uploads/{transfer_id}")
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "preview_ready"
    assert ready.json()["result"]["new_notes"] == 1
    assert ready.json()["result"]["preview_items"][0]["action"] == "import"

    apply = client.post(f"/v1/import/obsidian/uploads/{transfer_id}/apply", json={})
    assert apply.status_code == 202, apply.text
    transfers.run_vault_import_session(transfer_id, user_id)
    completed = client.get(f"/v1/import/obsidian/uploads/{transfer_id}")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["result"]["library_documents_imported"] == 1
    assert list(import_root.glob("*.part")) == []

    canceled = client.post(
        "/v1/import/obsidian/uploads",
        json={"filename": "cancel.zip", "expected_bytes": len(archive), "mode": "auto"},
    )
    canceled_id = canceled.json()["id"]
    cancel_response = client.post(f"/v1/import/obsidian/uploads/{canceled_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "canceled"
