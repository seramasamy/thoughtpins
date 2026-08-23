"""Validate the sanitized Thought Pins store review-notes template."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "deploy" / "store" / "review-notes-template.md"
PACKET = ROOT / "deploy" / "store" / "submission-packet.json"

SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
    re.compile(r"(?i)((?:api[_-]?key|auth[_-]?token|bot[_-]?token|jwt[_-]?secret)\s*[=:]\s*)[^\s,;'\"]+"),
    re.compile(r"(postgresql(?:\+psycopg2)?://)([^:@/]+):([^@/]+)@"),
    re.compile(r"(redis://)(:[^@/]+@)"),
]

FORBIDDEN_MARKERS = [
    "<password>",
    "<store-review-password>",
    "actual password",
    "todo",
    "tbd",
    "placeholder",
]

REQUIRED_TEXT = [
    "Thought Pins",
    "review@thoughtpins.com",
    "THOUGHTPINS_REVIEW_EMAIL",
    "THOUGHTPINS_REVIEW_PASSWORD",
    "python scripts/seed_review_account.py --export-vault --zip-vault",
    "private App Store Connect or Play Console review notes",
    "never committed to the repository",
    "https://thoughtpins.com",
    "https://thoughtpins.com/app",
    "https://api.thoughtpins.com/v1",
    "https://thoughtpins.com/privacy",
    "https://thoughtpins.com/terms",
    "https://thoughtpins.com/support",
    "https://thoughtpins.com/account/delete",
    "https://thoughtpins.com/ai-disclosure",
    "backend must remain live during review",
    "maintenance/offline banner",
    "login",
    "chat",
    "journal",
    "article/document",
    "upload",
    "memory cards",
    "export",
    "Delete the account",
    "Privacy",
    "AI disclosure",
    "POST /v1/chat",
    "POST /v1/library",
    "POST /v1/uploads",
    "/v1/memory/cards",
    "GET /v1/export",
    "DELETE /v1/me",
    "provider-neutral",
    "Journal content is not sold",
    "Private local adapters are separate from the submitted app",
    "not exposed in public web or native builds",
    "native UI projects",
    "deploy/store/native-review-handoff.json",
    "support@thoughtpins.com",
]


def main() -> int:
    failures = run_checks()
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Review notes packet check failed: {len(failures)} failure(s).")
        return 1
    print("Review notes packet check passed.")
    return 0


def run_checks() -> list[str]:
    failures: list[str] = []
    if not NOTES.is_file():
        return [f"Missing {NOTES.relative_to(ROOT)}"]
    if not PACKET.is_file():
        return [f"Missing {PACKET.relative_to(ROOT)}"]

    text = NOTES.read_text(encoding="utf-8-sig", errors="ignore")
    packet = json.loads(PACKET.read_text(encoding="utf-8-sig"))

    _check_no_secret_material(text, failures)
    _check_required_text(text, failures)
    _check_packet_consistency(text, packet, failures)
    _check_packet_references(packet, failures)
    return failures


def _check_no_secret_material(text: str, failures: list[str]) -> None:
    lowered = text.lower()
    for marker in FORBIDDEN_MARKERS:
        if marker in lowered:
            failures.append(f"review notes must not contain unresolved marker {marker!r}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append("review notes appear to contain secret-like material")


def _check_required_text(text: str, failures: list[str]) -> None:
    for marker in REQUIRED_TEXT:
        if marker not in text:
            failures.append(f"review notes missing required marker: {marker}")


def _check_packet_consistency(text: str, packet: dict[str, Any], failures: list[str]) -> None:
    raw_review = packet.get("review_access")
    review: dict[str, Any] = raw_review if isinstance(raw_review, dict) else {}
    for key, label in {
        "seed_command": "seed command",
        "default_email": "default email",
        "email_env_var": "email env var",
        "password_env_var": "password env var",
    }.items():
        value = review.get(key)
        if not isinstance(value, str) or value not in text:
            failures.append(f"review notes {label} must match submission packet")

    required_urls = {
        "marketing_site",
        "web_app",
        "api",
        "privacy_policy",
        "terms",
        "support",
        "account_deletion",
        "ai_disclosure",
    }
    raw_public_urls = packet.get("public_urls")
    public_urls: dict[str, Any] = raw_public_urls if isinstance(raw_public_urls, dict) else {}
    for key, value in public_urls.items():
        if key in required_urls and (not isinstance(value, str) or value not in text):
            failures.append(f"review notes missing public URL from submission packet: {key}")


def _check_packet_references(packet: dict[str, Any], failures: list[str]) -> None:
    if packet.get("review_notes_template") != "deploy/store/review-notes-template.md":
        failures.append("submission packet must reference deploy/store/review-notes-template.md")
    commands = set(packet.get("evidence_commands") or [])
    if "python scripts/check_review_notes_packet.py" not in commands:
        failures.append("submission packet evidence_commands must include review notes checker")


if __name__ == "__main__":
    raise SystemExit(main())
