"""Verify the closed-beta/App Review account packet is wired and safe.

The actual review password must be supplied by the deployment environment. This
check only verifies that the deterministic fictional seed, CLI, docs, and tests
are present and have the safety gates expected for a store review build.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _contains(relative: str, *needles: str) -> list[str]:
    text = _read(relative)
    return [f"{relative} missing {needle!r}" for needle in needles if needle not in text]


def _parse_python(relative: str) -> None:
    text = _read(relative)
    try:
        ast.parse(text, filename=relative)
    except SyntaxError as exc:
        raise AssertionError(f"{relative} is not valid Python: {exc}") from exc


def run_checks() -> list[str]:
    failures: list[str] = []

    expected_files = [
        "src/thoughtpins/review_seed.py",
        "scripts/seed_review_account.py",
        "tests/test_review_seed.py",
        "docs/release/APP_STORE_APPROVAL_PLAN.md",
        "docs/release/PRIVACY_AND_STORE_READINESS.md",
    ]
    for relative in expected_files:
        if not (ROOT / relative).is_file():
            failures.append(f"Missing {relative}")

    if failures:
        return failures

    for relative in [
        "src/thoughtpins/review_seed.py",
        "scripts/seed_review_account.py",
        "tests/test_review_seed.py",
    ]:
        _parse_python(relative)

    failures.extend(
        _contains(
            "src/thoughtpins/review_seed.py",
            "REVIEW_EMAIL_DEFAULT",
            "review@thoughtpins.com",
            "Refusing to seed review data in production",
            "delete_user_data",
            "VaultExporter",
            "Review Article - Attention and Recall",
            "Maya",
            "Atlas Cafe",
            "Copper Lantern",
        )
    )
    failures.extend(
        _contains(
            "scripts/seed_review_account.py",
            "THOUGHTPINS_REVIEW_PASSWORD",
            "--allow-production",
            "--export-vault",
            "--zip-vault",
            "not printed",
        )
    )
    failures.extend(
        _contains(
            "tests/test_review_seed.py",
            "/v1/auth/login",
            "/v1/memory/cards",
            "/v1/library",
            "/v1/export",
            "DELETE",
            "refuses_production_by_default",
        )
    )
    failures.extend(
        _contains(
            "docs/release/APP_STORE_APPROVAL_PLAN.md",
            "THOUGHTPINS_REVIEW_PASSWORD",
            "scripts/seed_review_account.py",
            "review@thoughtpins.com",
        )
    )
    failures.extend(
        _contains(
            "docs/release/PRIVACY_AND_STORE_READINESS.md",
            "THOUGHTPINS_REVIEW_PASSWORD",
            "scripts/seed_review_account.py",
            "Store review test account",
        )
    )

    seed_text = _read("src/thoughtpins/review_seed.py")
    if "sk-" in seed_text or "AAF" in seed_text or "jina_" in seed_text or "fc-" in seed_text:
        failures.append("review seed module appears to contain provider credentials")
    cli_text = _read("scripts/seed_review_account.py")
    if "print(password" in cli_text:
        failures.append("seed CLI may print the review password")
    if "Password: " in cli_text and "(not printed)" not in cli_text:
        failures.append("seed CLI password message must explicitly say it is not printed")

    return failures


def main() -> int:
    failures = run_checks()
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Review account packet check failed: {len(failures)} failure(s).")
        return 1
    print("Review account packet check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
