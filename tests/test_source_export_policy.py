from __future__ import annotations

import json


def test_third_party_source_body_is_excluded_from_account_and_vault_exports(
    isolated_db,
    monkeypatch,
    tmp_path,
):
    from thoughtpins import library
    from thoughtpins.data_lifecycle import export_user_data
    from thoughtpins.library import ingest_document_text
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.vault.exporter import VaultExporter

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    canary = "VIOLET-CANARY-ARTICLE-BODY must never appear in a portable export."
    source_text = (canary + " This source discusses durable memory and retrieval provenance. ") * 20
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("source-export-policy", session=session)
        result = ingest_document_text(
            session,
            source_text,
            user_id=user.id,
            source_type="article",
            title="Restricted Export Example",
            source_url="https://publisher.example/restricted-export-example",
            rights_basis="user_provided",
            paywall_detected=True,
        )

        payload = export_user_data(session, user.id)
        encoded = json.dumps(payload, sort_keys=True)
        assert canary not in encoded
        assert payload["source_export_policy"]["excluded_source_count"] == 1
        assert payload["tables"]["document_chunks"] == []
        assert not any(row.get("memory_type") == "source_excerpt" for row in payload["tables"]["memories"])
        exported_document = payload["tables"]["document_sources"][0]
        assert exported_document["id"] == result.document_id
        assert exported_document["source_text_included"] is False
        assert "raw_text" not in exported_document
        assert "summary" not in exported_document

        exporter = VaultExporter(session, user_id=user.id, vault_path=tmp_path / "vaults")
        stats = exporter.export_all(validate=True)
        assert stats["validation_errors"] == 0
        vault_text = "\n".join(path.read_text(encoding="utf-8") for path in exporter._vault.rglob("*.md"))
        assert canary not in vault_text
        assert "https://publisher.example/restricted-export-example" in vault_text
        assert "Third-party source text is excluded" in vault_text
        assert "## Extracted Text" not in vault_text
    finally:
        session.close()


def test_reusable_rights_allow_full_text_in_portable_exports(isolated_db, monkeypatch, tmp_path):
    from thoughtpins import library
    from thoughtpins.data_lifecycle import export_user_data
    from thoughtpins.library import ingest_document_text
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.vault.exporter import VaultExporter

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    reusable_text = "This openly licensed note should remain portable. " * 20
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("reusable-source-export", session=session)
        ingest_document_text(
            session,
            reusable_text,
            user_id=user.id,
            source_type="article",
            title="Reusable Source",
            source_url="https://repository.example/reusable",
            rights_basis="open_license",
        )

        payload = export_user_data(session, user.id)
        assert reusable_text.strip() in json.dumps(payload)
        exporter = VaultExporter(session, user_id=user.id, vault_path=tmp_path / "vaults")
        exporter.export_all(validate=True)
        vault_text = "\n".join(path.read_text(encoding="utf-8") for path in exporter._vault.rglob("*.md"))
        assert "## Extracted Text" in vault_text
        assert "This openly licensed note should remain portable" in vault_text
    finally:
        session.close()
