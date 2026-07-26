from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


def test_backup_restore_smoke_uses_scratch_target(monkeypatch, tmp_path):
    from thoughtpins import backup

    root = tmp_path / "app"
    data_dir = root / "data"
    vault_dir = root / "vault"
    reports_dir = root / "reports"
    qdrant_dir = data_dir / "qdrant"
    qdrant_dir.mkdir(parents=True)
    vault_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    (data_dir / "thoughtpins.sqlite3").write_text("sqlite bytes", encoding="utf-8")
    (qdrant_dir / ".lock").write_text("runtime lock", encoding="utf-8")
    (vault_dir / "daily.md").write_text("journal note", encoding="utf-8")
    (reports_dir / "summary.md").write_text("report", encoding="utf-8")

    def resolve_path(path: str | Path) -> Path:
        raw = str(path).replace("\\", "/").lstrip("./")
        return root / raw

    monkeypatch.setattr(backup.config, "resolve_path", resolve_path)
    monkeypatch.setattr(backup.config, "vault_path", lambda: vault_dir)
    monkeypatch.setattr(backup.config, "reports_path", lambda: reports_dir)
    monkeypatch.setattr(backup.config, "backups_path", lambda: root / "backups")

    info = backup.smoke_restore_backup(label="pytest", cleanup=True)

    assert info.backup_path.exists()
    provenance = backup.read_backup_provenance(info.backup_path)
    assert backup.sidecar_path(info.backup_path).exists()
    assert backup.checksum_path(info.backup_path).exists()
    assert provenance is not None and len(provenance["sha256"]) == 64
    assert info.restored_files >= 4
    assert set(info.included_roots) == {"data", "vault", "reports"}
    assert info.cleaned_up is True
    assert not info.target_path.exists()

    with zipfile.ZipFile(info.backup_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert "data/thoughtpins.sqlite3" in names
    assert "data/qdrant/.lock" not in names
    assert ".lock" in manifest["excluded_runtime_files"]


def test_backup_restore_uses_configured_sqlite_root_and_empty_dirs(monkeypatch, tmp_path):
    from thoughtpins import backup

    root = tmp_path / "app"
    configured_data = tmp_path / "isolated-runtime" / "data"
    vault_dir = tmp_path / "isolated-runtime" / "vault"
    reports_dir = tmp_path / "isolated-runtime" / "reports"
    vector_dir = tmp_path / "isolated-runtime" / "vectors"
    backups_dir = root / "backups"
    restore_dir = root / ".tmp" / "restore-smoke"
    for directory in (configured_data, vault_dir, reports_dir, vector_dir, backups_dir, restore_dir):
        directory.mkdir(parents=True, exist_ok=True)

    db_path = configured_data / "thoughtpins.sqlite3"
    db_path.write_text("sqlite bytes", encoding="utf-8")
    (vault_dir / "index.md").write_text("vault note", encoding="utf-8")
    (vector_dir / "segment.bin").write_bytes(b"vector bytes")

    def resolve_path(path: str | Path) -> Path:
        raw = str(path).replace("\\", "/").lstrip("./")
        return root / raw

    monkeypatch.setattr(backup.config, "resolve_path", resolve_path)
    monkeypatch.setattr(backup.config, "DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(backup.config, "database_url_sync", lambda: f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(backup.config, "database_path", lambda: str(db_path))
    monkeypatch.setattr(backup.config, "vault_path", lambda: vault_dir)
    monkeypatch.setattr(backup.config, "reports_path", lambda: reports_dir)
    monkeypatch.setattr(backup.config, "backups_path", lambda: backups_dir)
    monkeypatch.setattr(backup.config, "qdrant_path", lambda: vector_dir)

    info = backup.smoke_restore_backup(label="configured", cleanup=True)

    assert info.backup_path.exists()
    assert info.backup_path.parent == backups_dir
    assert {"data", "vault", "reports", "vectors"}.issubset(set(info.included_roots))
    assert info.cleaned_up is True

    with zipfile.ZipFile(info.backup_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert "data/thoughtpins.sqlite3" in names
    assert "vault/index.md" in names
    assert "vectors/segment.bin" in names
    assert "reports/" in names
    assert "reports" in manifest["included_roots"]


def test_restore_rejects_archive_modified_after_sidecar_creation(monkeypatch, tmp_path):
    from thoughtpins import backup

    root = tmp_path / "app"
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "thoughtpins.sqlite3").write_text("sqlite bytes", encoding="utf-8")
    monkeypatch.setattr(backup.config, "database_path", lambda: str(data_dir / "thoughtpins.sqlite3"))
    monkeypatch.setattr(
        backup.config, "database_url_sync", lambda: f"sqlite:///{(data_dir / 'thoughtpins.sqlite3').as_posix()}"
    )
    monkeypatch.setattr(backup.config, "vault_path", lambda: root / "vault")
    monkeypatch.setattr(backup.config, "reports_path", lambda: root / "reports")
    monkeypatch.setattr(backup.config, "backups_path", lambda: root / "backups")
    monkeypatch.setattr(backup.config, "qdrant_path", lambda: data_dir / "qdrant")

    created = backup.create_backup(label="tamper-test")
    with created.path.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(ValueError, match="SHA-256"):
        backup.restore_backup(created.path, target_root=root / "restore")


def test_pruning_removes_checksum_and_private_sidecar(monkeypatch, tmp_path):
    from thoughtpins import backup

    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    monkeypatch.setattr(backup.config, "backups_path", lambda: backup_root)
    old = backup_root / "thoughtpins_backup_2000-01-01_000000_old.zip"
    old.write_bytes(b"old")
    old_sidecar = backup.sidecar_path(old)
    old_checksum = backup.checksum_path(old)
    old_sidecar.write_text("{}", encoding="utf-8")
    old_checksum.write_text("0" * 64, encoding="utf-8")

    assert backup.prune_backups(keep=0) == 1
    assert not old.exists()
    assert not old_sidecar.exists()
    assert not old_checksum.exists()
