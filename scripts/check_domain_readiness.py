"""Validate Thought Pins public-domain release scaffolding."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_ENV = {
    "PRIVACY_POLICY_URL": "https://thoughtpins.com/privacy",
    "TERMS_URL": "https://thoughtpins.com/terms",
    "SUPPORT_URL": "https://thoughtpins.com/support",
    "ACCOUNT_DELETION_URL": "https://thoughtpins.com/account/delete",
    "AI_DISCLOSURE_URL": "https://thoughtpins.com/ai-disclosure",
    "WEB_APP_URL": "https://thoughtpins.com/app",
    "CORS_ALLOW_ORIGINS": "https://thoughtpins.com",
    "ANDROID_STORE_URL": "https://play.google.com/store/apps/details?id=com.thoughtpins.app",
}

REQUIRED_SITE_FILES = [
    "site/index.html",
    "site/privacy.html",
    "site/terms.html",
    "site/support.html",
    "site/ai-disclosure.html",
    "site/security.html",
    "site/account/delete/index.html",
    "site/assets/styles.css",
    "site/assets/site.js",
    "site/assets/site.webmanifest",
    "site/assets/thought-pins-mark.svg",
    "site/assets/product-chat-desktop.png",
    "site/robots.txt",
    "site/sitemap.xml",
]


REQUIRED_SITE_MARKERS = {
    "site/index.html": [
        "Thought Pins - Your memory, connected",
        # Keep the registration and control surfaces present without requiring
        # retired marketing headings. The export claim must still be visible.
        'data-primary-cta data-app-link="register" href="/app/?auth=register"',
        'id="keep" aria-labelledby="keep-title"',
        "Obsidian-compatible Markdown vault",
        "data-app-link",
    ],
    "site/privacy.html": [
        "Data categories",
        "Contact Info",
        "User Content",
        "Identifiers",
        "Diagnostics",
        "Journal and document content may be sent to configured third-party AI providers",
        "Thought Pins does not use journal content for advertising or cross-app tracking",
        "Account deletion removes user-scoped journal entries",
        "support@thoughtpins.com",
        "explicit permission",
        "does not defeat publisher controls",
    ],
    "site/account/delete/index.html": [
        "Delete Account",
        "delete their account and associated data",
        "Web deletion request",
        "request account deletion and associated data deletion",
        "What deletion removes",
        "Exports before deletion",
        "within 30 days",
        "support@thoughtpins.com",
    ],
    "site/ai-disclosure.html": [
        "AI Disclosure",
        "classify journal messages",
        "Human control",
        "Provider-neutral runtime",
        "No professional advice",
        "Safety and reporting",
        "unsafe AI output",
    ],
    "site/support.html": [
        "Support",
        "account deletion",
        "privacy",
        "support@thoughtpins.com",
        "AI safety reports",
        "unsafe AI output",
    ],
    "site/terms.html": [
        "Terms",
        "AI-assisted responses",
        "support@thoughtpins.com",
        "copyrighted articles",
        "defeat publisher, account, or license controls",
    ],
    "site/security.html": [
        "Tenant isolation",
        "Account and session security",
        "Responsible disclosure",
        "Local no-auth sessions",
        "security@thoughtpins.com",
    ],
}
REQUIRED_DEPLOY_FILES = [
    "deploy/DOMAIN_AND_DNS.md",
    "deploy/Caddyfile.thoughtpins.example",
    "deploy/dns-zone-template.txt",
    ".env.staging.example",
    "scripts/smoke_public_domain.py",
    "scripts/run_staging_smoke.ps1",
]


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    findings: list[str] = []
    env_path = ROOT / ".env.production.example"
    env = _parse_env(env_path)

    for key, expected in EXPECTED_ENV.items():
        actual = env.get(key)
        if actual != expected:
            findings.append(f"{env_path.name}: {key} must be {expected!r}, got {actual!r}")

    if "example.com" in env_path.read_text(encoding="utf-8"):
        findings.append(".env.production.example must not contain example.com placeholders for public app URLs")

    for rel in REQUIRED_SITE_FILES + REQUIRED_DEPLOY_FILES:
        if not (ROOT / rel).exists():
            findings.append(f"missing required domain file: {rel}")

    for rel in REQUIRED_SITE_FILES:
        path = ROOT / rel
        if not path.exists() or path.suffix.lower() not in {".html", ".txt", ".xml"}:
            continue
        page_text = path.read_text(encoding="utf-8")
        lowered = page_text.lower()
        if "placeholder" in lowered:
            findings.append(f"{rel}: public site content must not contain visible placeholder language")
        for marker in REQUIRED_SITE_MARKERS.get(rel, []):
            if marker not in page_text:
                findings.append(f"{rel}: missing public review marker {marker!r}")

    caddy_path = ROOT / "deploy" / "Caddyfile.thoughtpins.example"
    if caddy_path.exists():
        caddy = caddy_path.read_text(encoding="utf-8")
        for host in ("thoughtpins.com", "www.thoughtpins.com", "thoughtpins.com", "api.thoughtpins.com"):
            if host not in caddy:
                findings.append(f"{caddy_path.name}: missing host {host}")

    if findings:
        print("Domain readiness failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Domain readiness passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
