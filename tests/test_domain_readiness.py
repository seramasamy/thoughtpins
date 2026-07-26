from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_domain_readiness_check_passes_with_store_review_markers() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_domain_readiness.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Domain readiness passed." in result.stdout


def test_public_site_copy_covers_deletion_ai_and_data_safety() -> None:
    privacy = (ROOT / "site/privacy.html").read_text(encoding="utf-8-sig")
    deletion = (ROOT / "site/account/delete/index.html").read_text(encoding="utf-8-sig")
    ai = (ROOT / "site/ai-disclosure.html").read_text(encoding="utf-8-sig")
    security = (ROOT / "site/security.html").read_text(encoding="utf-8-sig")
    homepage = (ROOT / "site/index.html").read_text(encoding="utf-8-sig")

    for marker in ["Contact Info", "User Content", "Identifiers", "Diagnostics", "cross-app tracking"]:
        assert marker in privacy
    assert "Journal and document content may be sent to configured third-party AI providers" in privacy
    assert "Account deletion removes user-scoped journal entries" in privacy
    assert "does not defeat publisher controls" in privacy
    assert "explicit permission" in privacy

    assert "delete their account and associated data" in deletion
    assert "request account deletion and associated data deletion" in deletion
    assert "Exports before deletion" in deletion

    assert "Provider-neutral runtime" in ai
    assert "Human control" in ai
    assert "No professional advice" in ai
    assert "Safety and reporting" in ai
    assert "unsafe AI output" in ai

    assert "Your memory, connected" in homepage
    assert "Open test session" in (ROOT / "site/assets/site.js").read_text(encoding="utf-8-sig")
    assert "Tenant isolation" in security
    assert "Responsible disclosure" in security
