"""Resolve scholarly links to authorized open-access copies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_DOI_TRAILING_PUNCTUATION = ".,;:!?)]}"


@dataclass(frozen=True)
class OpenAccessCandidate:
    doi: str
    url: str
    landing_url: str
    pdf_url: str | None
    license: str | None
    host_type: str | None
    version: str | None
    rights_basis: str

    def as_metadata(self) -> dict[str, str | None]:
        return {
            "doi": self.doi,
            "url": self.url,
            "landing_url": self.landing_url,
            "pdf_url": self.pdf_url,
            "license": self.license,
            "host_type": self.host_type,
            "version": self.version,
            "rights_basis": self.rights_basis,
        }


def extract_doi(value: str) -> str | None:
    """Extract a normalized DOI from a DOI string or URL."""
    decoded = unquote((value or "").strip())
    match = _DOI_RE.search(decoded)
    if not match:
        return None
    return match.group(0).rstrip(_DOI_TRAILING_PUNCTUATION).lower()


def resolve_open_access(
    value: str,
    *,
    contact_email: str,
    base_url: str = "https://api.unpaywall.org/v2",
    timeout_seconds: int = 12,
    client: httpx.Client | None = None,
) -> OpenAccessCandidate | None:
    """Return a legal open copy reported by the configured scholarly index."""
    doi = extract_doi(value)
    if not doi or not contact_email.strip():
        return None

    endpoint = f"{base_url.rstrip('/')}/{quote(doi, safe='/')}"
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    try:
        response = http.get(endpoint, params={"email": contact_email.strip()})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            http.close()

    if not isinstance(payload, dict) or payload.get("is_oa") is not True:
        return None
    locations = _ordered_locations(payload)
    for location in locations:
        candidate = _candidate_from_location(doi, location)
        if candidate is not None:
            return candidate
    return None


def _ordered_locations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    raw_locations = payload.get("oa_locations")
    if isinstance(raw_locations, list):
        locations.extend(item for item in raw_locations if isinstance(item, dict) and item not in locations)
    return sorted(
        locations,
        key=lambda item: (
            str(item.get("host_type") or "").lower() != "repository",
            not bool(str(item.get("license") or "").strip()),
        ),
    )


def _candidate_from_location(doi: str, location: dict[str, Any]) -> OpenAccessCandidate | None:
    landing_url = str(location.get("url_for_landing_page") or location.get("url") or "").strip()
    pdf_url = str(location.get("url_for_pdf") or "").strip() or None
    preferred_url = landing_url or pdf_url or ""
    parsed = urlparse(preferred_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    license_name = str(location.get("license") or "").strip().lower() or None
    rights_basis = "open_license" if license_name else "open_access"
    return OpenAccessCandidate(
        doi=doi,
        url=preferred_url,
        landing_url=landing_url or preferred_url,
        pdf_url=pdf_url,
        license=license_name,
        host_type=str(location.get("host_type") or "").strip().lower() or None,
        version=str(location.get("version") or "").strip().lower() or None,
        rights_basis=rights_basis,
    )
