"""Transactional, encrypted chunk storage on the shared tenant database."""

from __future__ import annotations

from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import ENCRYPTED_BYTES_PREFIX, decrypt_bytes_scoped, encrypt_bytes_scoped
from thoughtpins.db_transfers import VaultImportChunk


def _scope(user_id: str, transfer_id: str) -> str:
    if not user_id or not transfer_id:
        raise ValueError("An owner and transfer identity are required")
    return f"vault-import:{user_id}:{transfer_id}"


def store_chunk(session: Session, *, user_id: str, transfer_id: str, offset: int, content: bytes) -> None:
    scope = _scope(user_id, transfer_id)
    encrypted = encrypt_bytes_scoped(content, scope=scope)
    if encrypted is None and config.is_production():
        raise RuntimeError("Vault upload encryption is unavailable")
    session.add(
        VaultImportChunk(
            user_id=user_id,
            transfer_id=transfer_id,
            offset=offset,
            byte_size=len(content),
            payload=encrypted if encrypted is not None else content,
        )
    )
    session.flush()


def read_range(session: Session, *, user_id: str, transfer_id: str, offset: int, size: int) -> bytes:
    scope = _scope(user_id, transfer_id)
    rows = (
        session.query(VaultImportChunk)
        .filter(
            VaultImportChunk.user_id == user_id,
            VaultImportChunk.transfer_id == transfer_id,
            VaultImportChunk.offset < offset + size,
            VaultImportChunk.offset + VaultImportChunk.byte_size > offset,
        )
        .order_by(VaultImportChunk.offset)
        .all()
    )
    result = bytearray()
    cursor = offset
    for row in rows:
        if row.offset > cursor:
            break
        content = bytes(row.payload)
        if content.startswith(ENCRYPTED_BYTES_PREFIX):
            plaintext = decrypt_bytes_scoped(content, scope=scope)
            if plaintext is None:
                raise RuntimeError("Staged vault archive cannot be decrypted")
            content = plaintext
        if len(content) != row.byte_size:
            raise RuntimeError("Staged vault chunk failed integrity verification")
        part = content[cursor - row.offset : offset + size - row.offset]
        result.extend(part)
        cursor += len(part)
    if len(result) != size:
        raise RuntimeError("Staged vault archive is unavailable")
    return bytes(result)


def has_chunks(session: Session, *, user_id: str, transfer_id: str) -> bool:
    return (
        session.query(VaultImportChunk.id)
        .filter(
            VaultImportChunk.user_id == user_id,
            VaultImportChunk.transfer_id == transfer_id,
        )
        .first()
        is not None
    )


def remove_chunks(session: Session, *, user_id: str, transfer_id: str) -> None:
    session.query(VaultImportChunk).filter(
        VaultImportChunk.user_id == user_id,
        VaultImportChunk.transfer_id == transfer_id,
    ).delete(synchronize_session=False)
