from __future__ import annotations

import hashlib

import pytest
from cryptography.fernet import Fernet


def test_shared_chunks_are_encrypted_scoped_and_removed_on_cancel(isolated_db, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.db import VaultImportChunk
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.vault.transfer_storage import read_range
    from thoughtpins.vault.transfers import (
        append_vault_import_chunk,
        cancel_vault_import_session,
        create_vault_import_session,
    )

    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    content = b"fictional private vault bytes"
    with get_session() as session:
        owner = get_or_create_default_user(session=session).id
        transfer = create_vault_import_session(
            session,
            user_id=owner,
            filename="fixture.zip",
            expected_bytes=len(content),
            archive_sha256=None,
            mode="auto",
            conflict_policy="skip",
        )
        append_vault_import_chunk(
            session,
            user_id=owner,
            transfer_id=transfer.id,
            offset=0,
            content=content,
            chunk_sha256=hashlib.sha256(content).hexdigest(),
        )
        row = session.query(VaultImportChunk).one()
        assert content not in row.payload
        assert read_range(session, user_id=owner, transfer_id=transfer.id, offset=0, size=len(content)) == content
        with pytest.raises(RuntimeError, match="unavailable"):
            read_range(session, user_id="another-user", transfer_id=transfer.id, offset=0, size=len(content))
        cancel_vault_import_session(session, user_id=owner, transfer_id=transfer.id)
        assert session.query(VaultImportChunk).count() == 0


def test_invalid_final_digest_rolls_back_only_the_unaccepted_chunk(isolated_db):
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.vault.transfer_storage import read_range
    from thoughtpins.vault.transfers import append_vault_import_chunk, create_vault_import_session

    with get_session() as session:
        owner = get_or_create_default_user(session=session).id
        transfer = create_vault_import_session(
            session,
            user_id=owner,
            filename="fixture.zip",
            expected_bytes=2,
            archive_sha256=hashlib.sha256(b"ab").hexdigest(),
            mode="auto",
            conflict_policy="skip",
        )
        transfer_id = transfer.id
        append_vault_import_chunk(
            session,
            user_id=owner,
            transfer_id=transfer_id,
            offset=0,
            content=b"a",
            chunk_sha256=hashlib.sha256(b"a").hexdigest(),
        )
        with pytest.raises(ValueError, match="Completed vault archive"):
            append_vault_import_chunk(
                session,
                user_id=owner,
                transfer_id=transfer_id,
                offset=1,
                content=b"x",
                chunk_sha256=hashlib.sha256(b"x").hexdigest(),
            )
        session.rollback()
        assert read_range(session, user_id=owner, transfer_id=transfer_id, offset=0, size=1) == b"a"
        completed = append_vault_import_chunk(
            session,
            user_id=owner,
            transfer_id=transfer_id,
            offset=1,
            content=b"b",
            chunk_sha256=hashlib.sha256(b"b").hexdigest(),
        )
        assert completed.status == "upload_ready"
