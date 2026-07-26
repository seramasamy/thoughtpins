"""Rights-aware retention and export decisions for saved sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class SourceRights(str, Enum):
    PUBLIC_DOMAIN = "public_domain"
    OPEN_LICENSE = "open_license"
    OPEN_ACCESS = "open_access"
    PUBLIC_WEB = "public_web"
    PUBLIC_FEED = "public_feed"
    USER_AUTHORED = "user_authored"
    USER_OWNED = "user_owned"
    USER_PROVIDED = "user_provided"
    METADATA_ONLY = "metadata_only"
    UNKNOWN = "unknown"


class SourceRecord(Protocol):
    source_type: str | None
    source_url: str | None
    access_method: str | None
    rights_basis: str | None
    paywall_detected: bool | None


@dataclass(frozen=True)
class SourceExportPolicy:
    include_source_text: bool
    include_source_chunks: bool
    include_extractive_summary: bool
    reason: str


_FULL_TEXT_RIGHTS = {
    SourceRights.PUBLIC_DOMAIN.value,
    SourceRights.OPEN_LICENSE.value,
    SourceRights.USER_AUTHORED.value,
    SourceRights.USER_OWNED.value,
}


def export_policy_for_source(source: SourceRecord) -> SourceExportPolicy:
    rights = (source.rights_basis or SourceRights.UNKNOWN.value).strip().lower()
    imported_user_note = (source.source_type or "").strip().lower() == "obsidian_note" and (
        source.access_method or ""
    ).strip().lower() == "obsidian_vault_import"
    portable_user_input = rights == SourceRights.USER_PROVIDED.value and not bool(source.paywall_detected)
    include_text = rights in _FULL_TEXT_RIGHTS or imported_user_note or portable_user_input
    if include_text:
        return SourceExportPolicy(
            True,
            True,
            True,
            "source text is user-provided, user-owned, or carries reusable rights",
        )
    return SourceExportPolicy(
        False,
        False,
        False,
        "third-party source text is excluded; metadata, provenance, and user-authored memory remain portable",
    )
