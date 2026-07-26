"""Privacy-preserving helpers for logs and operator diagnostics."""

from __future__ import annotations

import hashlib


def fingerprint_identifier(value: object | None) -> str:
    """Return a stable, non-reversible identifier for correlating logs."""
    if value is None:
        return "id:none"
    text = str(value).strip()
    if not text:
        return "id:none"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"id:{digest}"
