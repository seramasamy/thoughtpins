"""Tenant-owned encrypted originals in shared storage, independent of API disks."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import ENCRYPTED_BYTES_PREFIX, decrypt_bytes_scoped, encrypt_bytes_scoped
from thoughtpins.tenancy import get_current_tenant_id


def attachment_directory(user_id: str) -> Path:
    """The former per-tenant filesystem directory; retained for cleanup only."""
    if not user_id:
        raise ValueError("A tenant identity is required to store attachments")
    root = config.vault_path().resolve() / "09_Attachments"
    directory = root / hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    if root.is_symlink() or directory.is_symlink():
        raise RuntimeError("Unsafe attachment storage directory")
    return directory


def save_media_attachment(
    content: bytes,
    *,
    category: str,
    filename: str | None = None,
    user_id: str | None = None,
    session: Session | None = None,
) -> Path:
    """Return a portable reference; bytes live in the shared database, not a file."""
    from thoughtpins.db_storage import StoredAttachment
    from thoughtpins.store import get_session
    from thoughtpins.users import lock_active_user_for_write
    from thoughtpins.vault.markdown import safe_filename

    owner = user_id or get_current_tenant_id()
    if not owner:
        raise ValueError("A tenant identity is required to store attachments")
    if session is None:
        with get_session() as owned_session:
            result = save_media_attachment(
                content, category=category, filename=filename, user_id=owner, session=owned_session
            )
            owned_session.commit()
            return result
    lock_active_user_for_write(session, owner)
    label = safe_filename(category or "media", fallback="media", max_length=40)
    name = safe_filename(Path(filename or "upload.bin").name, fallback="upload.bin", max_length=100)
    reference = Path("09_Attachments") / hashlib.sha256(owner.encode()).hexdigest() / f"{label}-{uuid4().hex}-{name}"
    encrypted = encrypt_bytes_scoped(content, scope=f"attachments:{owner}")
    if encrypted is None and config.is_production():
        raise RuntimeError("Attachment encryption is unavailable")
    session.add(
        StoredAttachment(
            user_id=owner,
            reference=reference.as_posix(),
            original_filename=name,
            byte_size=len(content),
            payload=encrypted if encrypted is not None else content,
        )
    )
    session.flush()
    return reference


def export_attachments(user_id: str, target: Path) -> int:
    """Export only this account's originals, failing closed on decryption errors."""
    from thoughtpins.db_storage import StoredAttachment
    from thoughtpins.store import get_session
    from thoughtpins.users import lock_active_user_for_write

    if target.is_symlink():
        raise RuntimeError("Unsafe attachment export directory")
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    with get_session() as session:
        lock_active_user_for_write(session, user_id)
        rows = session.query(StoredAttachment).filter(StoredAttachment.user_id == user_id).yield_per(1)
        for row in rows:
            content = bytes(row.payload)
            if content.startswith(ENCRYPTED_BYTES_PREFIX):
                plaintext = decrypt_bytes_scoped(content, scope=f"attachments:{user_id}")
                if plaintext is None:
                    raise RuntimeError("Attachment decryption is unavailable")
                content = plaintext
            if len(content) != row.byte_size:
                raise RuntimeError("Attachment integrity verification failed")
            # Neither uploaded names nor stored metadata can escape the projection.
            name = f"{row.id}-{Path(row.original_filename).name}"
            destination = target / name
            if destination.is_symlink():
                raise RuntimeError("Unsafe attachment export destination")
            destination.write_bytes(content)
            destination.chmod(0o600)
            count += 1
    return count


def attachment_manifest(session: Session, user_id: str) -> list[dict]:
    """Describe the owner's originals without putting binary payloads in JSON."""
    from thoughtpins.db_storage import StoredAttachment

    rows = (
        session.query(
            StoredAttachment.id,
            StoredAttachment.reference,
            StoredAttachment.original_filename,
            StoredAttachment.byte_size,
            StoredAttachment.created_at_utc,
        )
        .filter(StoredAttachment.user_id == user_id)
        .all()
    )
    return [
        {
            "id": row.id,
            "reference": row.reference,
            "original_filename": row.original_filename,
            "byte_size": row.byte_size,
            "created_at_utc": row.created_at_utc.isoformat(),
            "vault_export_path": f"Attachments/{row.id}-{Path(row.original_filename).name}",
        }
        for row in rows
    ]


def purge_attachments(user_id: str) -> None:
    """Remove older filesystem storage. Relational originals use the user purge."""
    directory = attachment_directory(user_id)
    if directory.exists():
        shutil.rmtree(directory)
