"""App Store approval posture checks for Thought Pins.

This is a source-level gate for issues that tend to trigger review questions:
hidden local tools, public client config leaking runtime internals, missing
account/privacy/AI answers, weak native local-storage posture, and private
adapter drift. It complements the broader store packet and release checks.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIVATE_ADAPTER_FLAGS = (
    "telegram_enabled",
    "telegram_test_mode",
    "founder_test_mode_enabled",
)

_FORBIDDEN_PROVIDER_CODEPOINTS = (100, 101, 101, 112, 115, 101, 101, 107)
PROVIDER_NAME_FORBIDDEN = ("".join(map(chr, _FORBIDDEN_PROVIDER_CODEPOINTS)),)

PROVIDER_NEUTRAL_DIRS = (
    "src",
    "tests",
    "scripts",
    "frontend/src",
    "frontend/static",
    "site",
    "deploy",
    "mobile",
)

PUBLIC_UI_FORBIDDEN = (
    "Telegram Local Adapter",
    "Capture in Telegram",
    "Founder Telegram Test",
    "Founder mode",
    "local founder mode",
)

APPLE_ANSWER_MARKERS = (
    "What does the app do?",
    "Does the submitted app include hidden, beta, or owner-only features?",
    "What login methods are supported?",
    "Does the app use third-party AI?",
    "How is account deletion handled?",
    "What happens during backend maintenance?",
    "Does article ingestion defeat publisher access controls?",
    "What local data is stored on-device?",
    "What permissions are required?",
    "What code is submitted to stores?",
)

LOCAL_STORAGE_MARKERS = (
    "Keychain",
    "Android Keystore",
    "Offline draft queue",
    "Provider API keys",
    "Unbounded full-memory mirrors",
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/SessionStore.swift",
    "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/AndroidSecureStores.kt",
)

NATIVE_STORAGE_FILES = {
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/SessionStore.swift": (
        "import Security",
        "KeychainSessionStore",
        "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
    ),
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/DraftStore.swift": (
        "FileDraftStore",
        ".completeFileProtection",
        "suffix(250)",
    ),
    "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/AndroidSecureStores.kt": (
        "AndroidKeyStore",
        "AES/GCM/NoPadding",
        "AndroidSecureSessionStore",
        "AndroidEncryptedDraftStorage",
    ),
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/DraftQueue.kt": (
        "DraftQueue",
        "takeLast(250)",
        "Invalid journal text.",
    ),
}

PUBLIC_CLIENT_FILES = (
    "src/thoughtpins/api_routes/metadata.py",
    "frontend/src/types.ts",
    "frontend/static/app.js",
    "frontend/dist/index.html",
    "frontend/e2e/mockApi.ts",
)

PUBLIC_UI_FILES = (
    "frontend/src",
    "frontend/static/app.js",
    "frontend/dist",
    "site",
    "deploy/store/review-notes-template.md",
)


def main() -> int:
    failures: list[str] = []
    _check_public_client_config(failures)
    _check_public_ui_copy(failures)
    _check_provider_neutral_source(failures)
    _check_review_answers(failures)
    _check_local_storage(failures)
    _check_private_adapter_packet(failures)
    _check_review_notes(failures)
    _check_public_legal_site(failures)

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"App Store approval tilt check failed: {len(failures)} failure(s).")
        return 1
    print("App Store approval tilt check passed.")
    return 0


def _check_public_client_config(failures: list[str]) -> None:
    metadata = _read("src/thoughtpins/api_routes/metadata.py", failures)
    if not metadata:
        return
    for flag in PRIVATE_ADAPTER_FLAGS:
        if flag in metadata:
            failures.append(f"public client config exposes private adapter flag: {flag}")
    for marker in ('ai_processing="configured"',):
        if marker not in metadata:
            failures.append(f"public client config must expose generic AI-processing marker: {marker}")
    for field in ("llm_" + "provider", "llm_" + "model"):
        if field in metadata:
            failures.append("public client config must not expose provider/model fields")

    for rel in PUBLIC_CLIENT_FILES:
        text = _read(rel, failures)
        for flag in PRIVATE_ADAPTER_FLAGS:
            if flag in text:
                failures.append(f"{rel} contains private adapter flag {flag}")
    built_scripts = sorted((ROOT / "frontend" / "dist" / "assets").glob("*.js"))
    if not built_scripts:
        fallback = ROOT / "frontend" / "dist" / "app.js"
        built_scripts = [fallback] if fallback.is_file() else []
    if not built_scripts:
        failures.append("frontend production bundle has no JavaScript artifact")
    for path in built_scripts:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        for flag in PRIVATE_ADAPTER_FLAGS:
            if flag in text:
                failures.append(f"{path.relative_to(ROOT)} contains private adapter flag {flag}")


def _check_public_ui_copy(failures: list[str]) -> None:
    for rel in PUBLIC_UI_FILES:
        path = ROOT / rel
        paths = [path] if path.is_file() else list(path.rglob("*")) if path.exists() else []
        if not paths:
            failures.append(f"missing public UI path: {rel}")
            continue
        for child in paths:
            if child.suffix.lower() not in {".ts", ".tsx", ".js", ".html", ".md"}:
                continue
            text = child.read_text(encoding="utf-8-sig", errors="ignore")
            for marker in PUBLIC_UI_FORBIDDEN:
                if marker.lower() in text.lower():
                    failures.append(f"{child.relative_to(ROOT)} exposes private/test copy: {marker}")


def _check_provider_neutral_source(failures: list[str]) -> None:
    for rel in PROVIDER_NEUTRAL_DIRS:
        path = ROOT / rel
        if not path.exists():
            continue
        paths = [path] if path.is_file() else list(path.rglob("*"))
        for child in paths:
            if child.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".json", ".md", ".yml", ".yaml"}:
                continue
            text = child.read_text(encoding="utf-8-sig", errors="ignore").lower()
            for marker in PROVIDER_NAME_FORBIDDEN:
                if marker in text:
                    failures.append(
                        f"{child.relative_to(ROOT)} contains provider-specific public source marker: {marker}"
                    )


def _check_review_answers(failures: list[str]) -> None:
    text = _read("docs/release/APPLE_REVIEW_ANSWERS.md", failures)
    for marker in APPLE_ANSWER_MARKERS:
        if marker not in text:
            failures.append(f"docs/release/APPLE_REVIEW_ANSWERS.md missing reviewer answer: {marker}")
    for marker in ("account deletion", "third-party AI", "publisher access", "maintenance", "permissions"):
        if marker.lower() not in text.lower():
            failures.append(f"docs/release/APPLE_REVIEW_ANSWERS.md missing policy topic: {marker}")


def _check_local_storage(failures: list[str]) -> None:
    text = _read("docs/architecture/LOCAL_DEVICE_STORAGE.md", failures)
    for marker in LOCAL_STORAGE_MARKERS:
        if marker not in text:
            failures.append(f"docs/architecture/LOCAL_DEVICE_STORAGE.md missing storage marker: {marker}")

    for rel, markers in NATIVE_STORAGE_FILES.items():
        native = _read(rel, failures)
        for marker in markers:
            if marker not in native:
                failures.append(f"{rel} missing native storage marker: {marker}")


def _check_private_adapter_packet(failures: list[str]) -> None:
    packet = _json("deploy/store/submission-packet.json", failures)
    if not packet:
        return
    adapter = (packet.get("private_adapters") or {}).get("personal_chat_adapter") or {}
    if adapter.get("included_in_store_builds") is not False:
        failures.append("private adapter must be excluded from store builds")
    if adapter.get("included_in_public_github_export") is not False:
        failures.append("private adapter must be excluded from public GitHub export")
    if adapter.get("uses_public_api_only") is not True:
        failures.append("private adapter must use public API only")
    paths = set(adapter.get("required_public_api_paths") or [])
    for required in {"/v1/chat", "/v1/client-config", "/v1/health/deep", "/v1/export"}:
        if required not in paths:
            failures.append(f"private adapter packet missing API path: {required}")
    exclusions = packet.get("public_build_exclusions") or {}
    if exclusions.get("private_local_adapter_visible") is not False:
        failures.append("public build exclusions must hide private local adapters")
    if exclusions.get("client_config_exposes_private_adapter_flags") is not False:
        failures.append("public build exclusions must keep private adapter flags out of client config")


def _check_review_notes(failures: list[str]) -> None:
    text = _read("deploy/store/review-notes-template.md", failures)
    required = (
        "Private local adapters are separate from the submitted app",
        "not exposed in public web or native builds",
        "DELETE /v1/me",
        "POST /v1/safety/reports",
        "GET /v1/export",
    )
    for marker in required:
        if marker not in text:
            failures.append(f"review notes missing marker: {marker}")
    if "Telegram founder mode is local/test-only" in text:
        failures.append("review notes still use old local-adapter wording")


def _check_public_legal_site(failures: list[str]) -> None:
    required = {
        "site/privacy.html": (
            "third-party AI providers",
            "Users can export account data",
            "does not defeat publisher controls",
        ),
        "site/ai-disclosure.html": ("Provider-neutral runtime", "Human control", "Safety and reporting"),
        "site/support.html": ("AI safety reports", "unsafe AI output", "account deletion"),
        "site/account/delete/index.html": ("Delete Account", "within 30 days", "Exports before deletion"),
        "site/terms.html": ("copyrighted articles", "defeat publisher, account, or license controls", "Thought Pins"),
        "site/security.html": ("Tenant isolation", "Responsible disclosure", "Local no-auth sessions"),
    }
    for rel, markers in required.items():
        text = _read(rel, failures)
        for marker in markers:
            if marker not in text:
                failures.append(f"{rel} missing legal marker: {marker}")


def _read(relative: str, failures: list[str]) -> str:
    path = ROOT / relative
    if not path.is_file():
        failures.append(f"missing file: {relative}")
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _json(relative: str, failures: list[str]) -> dict:
    text = _read(relative, failures)
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception as exc:
        failures.append(f"invalid JSON in {relative}: {exc}")
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
