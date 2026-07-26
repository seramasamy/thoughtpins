"""Authenticated encryption helpers for private text and binary user data."""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet

from thoughtpins.config import config

ENCRYPTED_PREFIX = "enc:v1:"
ENCRYPTED_BYTES_PREFIX = b"tp:enc:v1:"


def _get_fernet() -> Fernet | None:
    key = config.DATA_ENCRYPTION_KEY
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        return None


def _master_key_bytes() -> bytes | None:
    key = config.DATA_ENCRYPTION_KEY
    if not key:
        return None
    try:
        decoded = base64.urlsafe_b64decode(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None
    return decoded if len(decoded) == 32 else None


def _get_scoped_fernet(scope: str) -> Fernet | None:
    """Derive a purpose-scoped key so one data class never reuses another's key."""

    master = _master_key_bytes()
    if master is None or not scope:
        return None
    derived = hmac.new(master, f"thoughtpins:{scope}".encode("utf-8"), hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_text(plaintext: str) -> str | None:
    f = _get_fernet()
    if f is None:
        return None
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def encrypt_bytes(plaintext: bytes) -> bytes | None:
    """Encrypt bytes without first converting sensitive content to text."""

    f = _get_fernet()
    if f is None:
        return None
    return ENCRYPTED_BYTES_PREFIX + f.encrypt(plaintext)


def decrypt_text(ciphertext: str) -> str | None:
    if ciphertext.startswith(ENCRYPTED_PREFIX):
        ciphertext = ciphertext[len(ENCRYPTED_PREFIX) :]
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def decrypt_bytes(ciphertext: bytes) -> bytes | None:
    """Decrypt data produced by :func:`encrypt_bytes`."""

    if ciphertext.startswith(ENCRYPTED_BYTES_PREFIX):
        ciphertext = ciphertext[len(ENCRYPTED_BYTES_PREFIX) :]
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext)
    except Exception:
        return None


def encrypt_bytes_scoped(plaintext: bytes, *, scope: str) -> bytes | None:
    """Encrypt binary data with a key derived for one tenant and purpose."""

    f = _get_scoped_fernet(scope)
    if f is None:
        return None
    return ENCRYPTED_BYTES_PREFIX + f.encrypt(plaintext)


def decrypt_bytes_scoped(ciphertext: bytes, *, scope: str) -> bytes | None:
    """Decrypt data produced by :func:`encrypt_bytes_scoped`."""

    if ciphertext.startswith(ENCRYPTED_BYTES_PREFIX):
        ciphertext = ciphertext[len(ENCRYPTED_BYTES_PREFIX) :]
    f = _get_scoped_fernet(scope)
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext)
    except Exception:
        return None


def fingerprint_bytes(plaintext: bytes, *, scope: str) -> str | None:
    """Return a non-reversible, tenant-scoped integrity fingerprint."""

    master = _master_key_bytes()
    if master is None or not scope:
        return None
    fingerprint_key = hmac.new(
        master,
        f"thoughtpins:fingerprint:{scope}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.new(fingerprint_key, plaintext, hashlib.sha256).hexdigest()


def encryption_available() -> bool:
    """Return whether the configured key is valid without exposing the key."""

    return _get_fernet() is not None


def encrypt_for_storage(plaintext: str) -> str | None:
    encrypted = encrypt_text(plaintext)
    return f"{ENCRYPTED_PREFIX}{encrypted}" if encrypted else None


def maybe_decrypt_text(value: str) -> str:
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    decrypted = decrypt_text(value)
    return decrypted if decrypted is not None else "[encrypted private entry]"


def generate_key() -> str:
    return Fernet.generate_key().decode("utf-8")
