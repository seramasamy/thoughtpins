"""Fail closed if paid-product plumbing appears in the free launch build."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "deploy" / "store" / "commerce-policy.json"
DEPENDENCY_FILES = (
    ROOT / "frontend" / "package.json",
    ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Package.swift",
    ROOT / "mobile" / "ios" / "ThoughtPinsCore" / "Package.swift",
    ROOT / "mobile" / "android" / "thoughtpins-app" / "build.gradle.kts",
    ROOT / "mobile" / "android" / "thoughtpins-core" / "build.gradle.kts",
)
USER_INTERFACE_ROOTS = (
    ROOT / "frontend" / "src",
    ROOT / "site",
    ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources",
    ROOT / "mobile" / "android" / "thoughtpins-app" / "src" / "main",
)
PAID_DEPENDENCY_MARKERS = (
    "storekit",
    "billingclient",
    "stripe",
    "paddle",
    "revenuecat",
    "purchases-ios",
    "purchases-android",
)
PURCHASE_UI_MARKERS = (
    "subscribe now",
    "start free trial",
    "buy now",
    "unlock premium",
    "upgrade plan",
    "manage subscription",
)


def main() -> int:
    failures: list[str] = []
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Free-launch check failed to run: {exc}")
        return 2

    expected = {
        "schema_version": 1,
        "access_model": "free",
        "subscriptions_enabled": False,
        "in_app_purchases_enabled": False,
        "external_purchase_links_enabled": False,
        "advertising_enabled": False,
        "future_monetization_requires_new_review": True,
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            failures.append(f"commerce-policy.json must set {key} to {value!r}")

    for path in DEPENDENCY_FILES:
        if not path.exists():
            failures.append(f"missing dependency manifest: {path.relative_to(ROOT).as_posix()}")
            continue
        lower = path.read_text(encoding="utf-8").lower()
        for marker in PAID_DEPENDENCY_MARKERS:
            if marker in lower:
                failures.append(f"{path.relative_to(ROOT).as_posix()}: paid dependency marker '{marker}'")

    for base in USER_INTERFACE_ROOTS:
        if not base.exists():
            failures.append(f"missing UI root: {base.relative_to(ROOT).as_posix()}")
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {
                ".html",
                ".js",
                ".ts",
                ".tsx",
                ".swift",
                ".kt",
                ".xml",
            }:
                continue
            lower = path.read_text(encoding="utf-8", errors="ignore").lower()
            for marker in PURCHASE_UI_MARKERS:
                if marker in lower:
                    failures.append(f"{path.relative_to(ROOT).as_posix()}: purchase UI marker '{marker}'")

    terms = (ROOT / "site" / "terms.html").read_text(encoding="utf-8").lower()
    if "current release is available without a subscription charge" not in terms:
        failures.append("site/terms.html must disclose the current free release")

    if failures:
        print("Free-launch check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Free-launch check passed: no subscription, purchase, advertising, or paid-SDK surface is enabled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
