from __future__ import annotations

import zipfile

import pytest


@pytest.mark.parametrize("production,asynchronous", [(True, False), (False, True)])
def test_hosted_ingestion_keeps_originals_off_worker_disk_but_allows_explicit_export(
    isolated_db, tmp_path, monkeypatch, production, asynchronous
):
    from thoughtpins.config import config
    from thoughtpins.data_lifecycle import delete_user_data
    from thoughtpins.db import StoredAttachment
    from thoughtpins.ingestion import service, vault_export
    from thoughtpins.media.attachments import save_media_attachment
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.vault.exporter import VaultExporter

    original = b"Fictional original retained only in the owning shared store."
    with get_session() as session:
        owner = get_or_create_default_user(session=session).id
        save_media_attachment(original, category="document", filename="fixture.txt", user_id=owner, session=session)
        session.commit()
        worker_root = tmp_path / "worker"
        api_root = tmp_path / "api"
        monkeypatch.setattr(config, "vault_path", lambda: worker_root)
        monkeypatch.setattr(config, "is_production", lambda: production)
        monkeypatch.setattr(config, "PROCESS_ENTRIES_ASYNC", asynchronous)
        monkeypatch.setattr(vault_export, "_last_export_time", 0.0)
        service._maybe_export_vault(session, owner, "fictional-entry")
        assert not worker_root.exists()
        assert session.query(StoredAttachment).filter(StoredAttachment.user_id == owner).count() == 1

        monkeypatch.setattr(config, "vault_path", lambda: api_root)
        stats = VaultExporter(session, user_id=owner).export_all(package_zip=True)
        with zipfile.ZipFile(stats["zip_path"]) as archive:
            paths = [n for n in archive.namelist() if n.startswith("Attachments/") and not n.endswith("/")]
            assert len(paths) == 1 and archive.read(paths[0]) == original
        delete_user_data(session, owner)
        assert not (api_root / owner).exists()
        assert not (api_root / f"{owner}.zip").exists()
        assert not worker_root.exists()
        assert session.query(StoredAttachment).filter(StoredAttachment.user_id == owner).count() == 0


def test_synchronous_local_ingestion_retains_its_scoped_vault_projection(isolated_db, tmp_path, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.ingestion import service, vault_export
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(config, "vault_path", lambda: tmp_path / "local")
    monkeypatch.setattr(config, "is_production", lambda: False)
    monkeypatch.setattr(config, "PROCESS_ENTRIES_ASYNC", False)
    monkeypatch.setattr(vault_export, "_last_export_time", 0.0)
    with get_session() as session:
        owner = get_or_create_default_user(session=session).id
        service._maybe_export_vault(session, owner, "fictional-entry")
    assert (tmp_path / "local" / owner / "Vault Home.md").is_file()
