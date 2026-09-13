"""A populated upload store must never be dropped as a routine rollback."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect


@pytest.mark.parametrize("table", ["stored_attachments", "vault_import_chunks"])
def test_downgrade_preserves_populated_storage(isolated_db, table, monkeypatch):
    from thoughtpins.db import StoredAttachment, VaultImportChunk, VaultImportSession
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import utcnow

    path = Path(__file__).parents[1] / "alembic/versions/0027_vault_import_chunks.py"
    spec = importlib.util.spec_from_file_location("_shared_upload_migration_fixture", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with get_session() as session:
        owner = get_or_create_default_user(session=session).id
        if table == "stored_attachments":
            session.add(
                StoredAttachment(
                    user_id=owner, reference="fixture", original_filename="fixture.txt", byte_size=1, payload=b"x"
                )
            )
        else:
            transfer = VaultImportSession(
                user_id=owner,
                filename="fixture.zip",
                expected_bytes=1,
                storage_key="fixture",
                mode="auto",
                conflict_policy="skip",
                expires_at_utc=utcnow(),
            )
            session.add(transfer)
            session.flush()
            session.add(VaultImportChunk(user_id=owner, transfer_id=transfer.id, offset=0, byte_size=1, payload=b"x"))
        session.commit()
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(session.connection())))
        with pytest.raises(RuntimeError, match="Migrate original attachments"):
            migration.downgrade()
        assert {"stored_attachments", "vault_import_chunks"}.issubset(inspect(session.connection()).get_table_names())
