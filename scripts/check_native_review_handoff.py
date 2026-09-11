"""Validate native-review source coverage without claiming unavailable device proof."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "deploy" / "store" / "native-review-handoff.json"
POLICY = ROOT / "deploy" / "store" / "store-policy-requirements.json"
SUBMISSION_PACKET = ROOT / "deploy" / "store" / "submission-packet.json"

REQUIRED_FLOW_IDS = {
    "email_phone_signup_login",
    "apple_google_oauth_parity",
    "chat_first_memory_surface",
    "journal_capture_and_processing",
    "article_document_ingestion",
    "memory_cards_and_provenance",
    "vault_export",
    "account_deletion_in_app_and_web",
    "legal_support_ai_disclosure",
    "maintenance_offline_and_retry",
    "device_registration_and_notifications_later",
}

REQUIRED_NATIVE_BLOCKER_MARKERS = [
    "Xcode archive",
    "signing",
    "screenshots",
    "device/simulator smoke tests",
    "live review backend",
]

REQUIRED_NATIVE_SHELL_FILES = {
    "ios": [
        "mobile/ios/ThoughtPinsApp/Package.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsAppModel.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsUploads.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsNativeProviders.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsReviewShell.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsScreens.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsAuthView.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsMainShell.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsChatScreen.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsChatComposer.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsChatSubmission.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsChatWelcome.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsRecapScreen.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsCollectionScreens.swift",
        "mobile/ios/ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsDesignComponents.swift",
        "mobile/ios/ThoughtPinsNative/project.yml",
        "mobile/ios/ThoughtPinsNative/Resources/Info.plist",
        "mobile/ios/ThoughtPinsNative/Resources/PrivacyInfo.xcprivacy",
        "mobile/ios/ThoughtPinsNative/Resources/ThoughtPins.entitlements",
        "mobile/ios/ThoughtPinsNative/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png",
    ],
    "android": [
        "mobile/android/settings.gradle.kts",
        "mobile/android/build.gradle.kts",
        "mobile/android/gradlew.bat",
        "mobile/android/gradle/verification-metadata.xml",
        "mobile/android/thoughtpins-app/build.gradle.kts",
        "mobile/android/thoughtpins-app/src/main/AndroidManifest.xml",
        "mobile/android/thoughtpins-app/src/main/res/xml/network_security_config.xml",
        "mobile/android/thoughtpins-app/src/main/res/drawable/ic_launcher_foreground.xml",
        "mobile/android/thoughtpins-app/src/main/res/mipmap-anydpi/ic_launcher.xml",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ThoughtPinsActivity.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/AndroidSecureStores.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/AndroidGoogleOAuthTokenProvider.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsAppShell.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsAuthScreens.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsMainShell.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsFeatureScreens.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsAccountScreen.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsTheme.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsUiComponents.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsUiState.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/NativeContracts.kt",
        "mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsViewModel.kt",
    ],
}

REQUIRED_NATIVE_SHELL_MARKERS = {
    "ios": [
        "import SwiftUI",
        "ThoughtPinsRootView",
        "ThoughtPinsAuthView",
        "ThoughtPinsOAuthProvider",
        "ThoughtPinsOAuthTokenProvider",
        "oauthLogin(provider:",
        "SignInWithAppleButton",
        "configureAppleSignInRequest",
        "credential.state == expectedState",
        "aiProcessingConsentAccepted",
        "I understand and allow this processing.",
        "ThoughtPinsUploadProvider",
        "ThoughtPinsUploadDestination",
        "ThoughtPinsDocumentPickerUploadProvider",
        "UniformTypeIdentifiers",
        "fileImporter(",
        "Data(contentsOf:",
        "base64EncodedString()",
        "startAccessingSecurityScopedResource",
        "uploadSelectedFile(destination:",
        "uploadFile(",
        "ThoughtPinsChatScreen",
        "isThinking",
        "Thinking with your memory",
        "Use private memories",
        "Private memories stay out of replies.",
        ".submitLabel(.send)",
        ".onSubmit(submit)",
        "Response voice",
        "responseStyle",
        "ThoughtPinsCaptureScreen",
        "ThoughtPinsLibraryScreen",
        "ThoughtPinsMemoryScreen",
        "ThoughtPinsAccountScreen",
        "Legal and support",
        "Privacy Policy",
        "Account Deletion",
        "AI Disclosure",
        "legalURL(configured:",
        "acceptLegal(document:",
        'Link("Privacy Policy"',
        "maintenanceMessage",
        "syncDrafts",
        "deleteAccount",
        "exportAccount",
        "ingestLink",
        ".confirmationDialog(",
        "NSPrivacyTracking",
        "PRODUCT_BUNDLE_IDENTIFIER: com.thoughtpins.app",
    ],
    "android": [
        "@Composable",
        "ThoughtPinsApp",
        "ThoughtPinsAuthScreen",
        "aiProcessingConsentAccepted",
        "NativeOAuthTokenProvider",
        "AndroidGoogleOAuthTokenProvider",
        "GetSignInWithGoogleOption",
        "GoogleIdTokenCredential",
        "oauthTokenProvider = oauthProvider",
        "I understand and allow this processing.",
        "NativeUploadProvider",
        "NativeUploadDestination",
        "uploadSelectedFile(destination:",
        "uploadFile(",
        "AndroidFileUploadProvider",
        "ActivityResultContracts.OpenDocument",
        "contentResolver.openInputStream",
        "Base64.encodeToString",
        "uploadProvider = AndroidFileUploadProvider",
        "ThoughtPinsChatScreen",
        "isThinking",
        "Thinking with your memory",
        "Use private memories",
        "Private memories stay out of replies.",
        "Record a voice note",
        "ImeAction.Send",
        "KeyboardActions(onSend",
        "Response voice",
        "responseStyle",
        "ThoughtPinsCaptureScreen",
        "ThoughtPinsLibraryScreen",
        "ThoughtPinsMemoryCardsScreen",
        "ThoughtPinsAccountScreen",
        "Legal and support",
        "Privacy Policy",
        "Account Deletion",
        "AI Disclosure",
        "legalUrl(configured:",
        "acceptLegal",
        "NativeExternalLinkOpener",
        "openLegalLink",
        "AndroidExternalLinkOpener",
        "Intent.ACTION_VIEW",
        "maintenanceMessage",
        "deleteAccount",
        "exportAccount",
        "ingestLink",
        "AndroidSecureSessionStore",
        "AndroidEncryptedDraftStorage",
        "KeyGenParameterSpec",
        "DraftQueue",
        "syncDrafts",
        "AlertDialog(",
        'android:usesCleartextTraffic="false"',
        "compileSdk = 37",
        "ic_launcher_foreground",
    ],
}
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
]

NATIVE_PACKAGE_ROOTS = [
    "mobile/ios/ThoughtPinsNative/Sources",
    "mobile/ios/ThoughtPinsNative/Resources",
    "mobile/ios/ThoughtPinsApp/Sources",
    "mobile/ios/ThoughtPinsCore/Sources",
    "mobile/android/thoughtpins-app/src/main",
    "mobile/android/thoughtpins-core/src/main",
]
FORBIDDEN_NATIVE_SUFFIXES = {".db", ".env", ".log", ".md", ".sqlite3", ".txt", ".zip"}
FORBIDDEN_NATIVE_MARKERS = (
    "telegram",
    "founder mode",
    "jina_",
    "firecrawl",
    "apify",
    "deep" + "seek",
    "pay" + "wall by" + "pass",
    "by" + "pass pay" + "wall",
    "access-control evasion",
    "c:\\users\\",
)


def main() -> int:
    failures: list[str] = []
    handoff = _load_json(HANDOFF, failures)
    policy = _load_json(POLICY, failures)
    packet = _load_json(SUBMISSION_PACKET, failures)
    if not handoff or not policy or not packet:
        return _finish(failures)

    _check_status(handoff, failures)
    _check_paths(handoff, failures)
    _check_native_shells(handoff, failures)
    _check_flows(handoff, policy, failures)
    _check_native_blockers(handoff, failures)
    _check_submission_packet(packet, failures)
    _check_native_package_boundaries(failures)
    _check_no_secrets(HANDOFF, failures)
    return _finish(failures)


def _load_json(path: Path, failures: list[str]) -> dict:
    if not path.is_file():
        failures.append(f"Missing JSON file: {path.relative_to(ROOT)}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        failures.append(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}


def _check_status(handoff: dict, failures: list[str]) -> None:
    if handoff.get("app_name") != "Thought Pins":
        failures.append("native handoff app_name must be Thought Pins")
    status = handoff.get("status") or {}
    if status.get("closed_beta_web_handoff_ready") is not True:
        failures.append("native handoff must mark closed_beta_web_handoff_ready=true")
    if status.get("native_core_ready") is not True:
        failures.append("native handoff must mark native_core_ready=true")
    if status.get("native_ui_shells_ready") is not True:
        failures.append("native handoff must mark native_ui_shells_ready=true once source shells exist")
    if status.get("native_store_submission_ready") is not False:
        failures.append(
            "native handoff must keep native_store_submission_ready=false until native builds, signing, screenshots, and device proof exist"
        )
    if not str(status.get("native_store_submission_reason") or "").strip():
        failures.append("native handoff must explain why native store submission is not ready")


def _check_paths(handoff: dict, failures: list[str]) -> None:
    for key in ["official_policy_map", "mobile_contract", "web_reference_client"]:
        value = handoff.get(key)
        if not isinstance(value, str) or not (ROOT / value).is_file():
            failures.append(f"native handoff {key} must point to an existing file")
    modules = handoff.get("native_core_modules") or {}
    for key in ["ios", "android"]:
        value = modules.get(key)
        if not isinstance(value, str) or not (ROOT / value).exists():
            failures.append(f"native handoff native_core_modules.{key} must point to an existing path")


def _check_native_shells(handoff: dict, failures: list[str]) -> None:
    modules = handoff.get("native_app_shell_modules") or {}
    for platform, files in REQUIRED_NATIVE_SHELL_FILES.items():
        module_path = modules.get(platform)
        if not isinstance(module_path, str) or not (ROOT / module_path).exists():
            failures.append(f"native handoff native_app_shell_modules.{platform} must point to an existing path")
        text = _combined_text(files)
        for relative in files:
            path = ROOT / relative
            if not path.is_file():
                failures.append(f"missing native {platform} shell file: {relative}")
            elif path.suffix in {".swift", ".kt", ".kts"}:
                _check_balanced_delimiters(relative, path.read_text(encoding="utf-8-sig", errors="ignore"), failures)
        for marker in REQUIRED_NATIVE_SHELL_MARKERS[platform]:
            if marker not in text:
                failures.append(f"native {platform} shell missing marker: {marker}")
    android_manifest = _combined_text(["mobile/android/thoughtpins-app/src/main/AndroidManifest.xml"])
    if "android:screenOrientation" in android_manifest:
        failures.append("Android review target must not lock device orientation")
    if 'android:resizeableActivity="true"' not in android_manifest:
        failures.append("Android review target must explicitly support resizable tablet and landscape layouts")


def _check_native_package_boundaries(failures: list[str]) -> None:
    """Keep local operations, credentials, and internal notes out of store binaries."""
    for relative_root in NATIVE_PACKAGE_ROOTS:
        root = ROOT / relative_root
        if not root.is_dir():
            failures.append(f"missing native package root: {relative_root}")
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix.lower() in FORBIDDEN_NATIVE_SUFFIXES or path.name.lower().startswith(".env"):
                failures.append(f"native package contains non-product artifact: {relative}")
                continue
            if path.suffix.lower() not in {
                ".entitlements",
                ".json",
                ".kt",
                ".kts",
                ".plist",
                ".png",
                ".swift",
                ".svg",
                ".xcprivacy",
                ".xml",
            }:
                continue
            if path.suffix.lower() == ".png":
                continue
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            lowered = text.lower()
            for marker in FORBIDDEN_NATIVE_MARKERS:
                if marker in lowered:
                    failures.append(f"native package exposes private/internal marker {marker!r}: {relative}")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(f"native package contains a secret-like token: {relative}")


def _check_flows(handoff: dict, policy: dict, failures: list[str]) -> None:
    flows = handoff.get("required_review_flows") or []
    if not isinstance(flows, list):
        failures.append("native handoff required_review_flows must be a list")
        return
    by_id: dict[str, dict[str, object]] = {}
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        flow_id = flow.get("id")
        if isinstance(flow_id, str):
            by_id[flow_id] = {str(key): value for key, value in flow.items() if isinstance(key, str)}
        else:
            failures.append("native handoff flow missing string id")
    missing = REQUIRED_FLOW_IDS - by_id.keys()
    if missing:
        failures.append(f"native handoff missing required flows: {sorted(missing)}")
    unexpected = by_id.keys() - REQUIRED_FLOW_IDS
    if unexpected:
        failures.append(f"native handoff has unexpected flows: {sorted(unexpected)}")

    policy_ids: set[str] = set()
    requirements = policy.get("requirements")
    if isinstance(requirements, list):
        for item in requirements:
            if isinstance(item, dict):
                policy_id = item.get("id")
                if isinstance(policy_id, str):
                    policy_ids.add(policy_id)

    ios_text = _combined_text(
        [
            "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/APIClient.swift",
            "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/Models.swift",
            "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/DraftStore.swift",
            "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/VersionPolicy.swift",
        ]
    )
    android_text = _combined_text(
        [
            "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/ThoughtPinsApiClient.kt",
            "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/Models.kt",
            "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/DraftQueue.kt",
            "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/VersionPolicy.kt",
        ]
    )
    repo_contract_text = _combined_text(
        [
            "docs/architecture/MOBILE_API_CONTRACT.md",
            "src/thoughtpins/api.py",
            # The maintenance refusal lives here since api.py reached its size
            # ratchet; the evidence is the behaviour, not the filename.
            "src/thoughtpins/api_gateway.py",
            "src/thoughtpins/api_routes/public.py",
        ]
    )

    for flow_id, flow in by_id.items():
        web_reference = flow.get("web_reference")
        if not isinstance(web_reference, str) or not (ROOT / web_reference).is_file():
            failures.append(f"flow {flow_id} web_reference must point to an existing file")
        for policy_id in _string_list(flow.get("store_relevance")):
            if policy_id not in policy_ids:
                failures.append(f"flow {flow_id} references unknown policy requirement {policy_id}")
        _check_markers(flow_id, "ios_core_evidence", _string_list(flow.get("ios_core_evidence")), ios_text, failures)
        _check_markers(
            flow_id, "android_core_evidence", _string_list(flow.get("android_core_evidence")), android_text, failures
        )
        _check_markers(
            flow_id, "backend_evidence", _string_list(flow.get("backend_evidence")), repo_contract_text, failures
        )
        status = str(flow.get("native_ui_status") or "")
        if not status or not any(token in status for token in {"pending", "core_ready", "shell_ready"}):
            failures.append(f"flow {flow_id} native_ui_status must state pending/core-ready/shell-ready status")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _check_markers(flow_id: str, field: str, markers: list[str], haystack: str, failures: list[str]) -> None:
    if not markers:
        failures.append(f"flow {flow_id} must include {field}")
        return
    for marker in markers:
        if _is_endpoint_or_url(marker):
            continue
        if marker not in haystack:
            failures.append(f"flow {flow_id} {field} marker not found: {marker}")


def _check_native_blockers(handoff: dict, failures: list[str]) -> None:
    blockers = handoff.get("native_submission_blockers") or []
    if not isinstance(blockers, list) or len(blockers) < 4:
        failures.append("native handoff must list concrete native_submission_blockers")
        return
    joined = "\n".join(str(item) for item in blockers)
    for marker in REQUIRED_NATIVE_BLOCKER_MARKERS:
        if marker not in joined:
            failures.append(f"native_submission_blockers missing marker: {marker}")


def _check_submission_packet(packet: dict, failures: list[str]) -> None:
    blockers = packet.get("known_external_blockers_before_submission") or []
    joined = "\n".join(str(item) for item in blockers)
    for marker in ["native iOS/Android", "screenshots"]:
        if marker not in joined:
            failures.append(f"submission packet known blockers should mention {marker}")
    commands = set(packet.get("evidence_commands") or [])
    if "python scripts/check_ios_submission_source.py" not in commands:
        failures.append("submission packet evidence_commands must include check_ios_submission_source.py")
    if "python scripts/check_native_review_handoff.py" not in commands:
        failures.append("submission packet evidence_commands must include check_native_review_handoff.py")


def _combined_text(relative_paths: list[str]) -> str:
    parts: list[str] = []
    for relative in relative_paths:
        path = ROOT / relative
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def _is_endpoint_or_url(value: str) -> bool:
    if (ROOT / value).exists():
        return True
    if (
        value.startswith("/")
        or " /v1/" in value
        or value.startswith("GET ")
        or value.startswith("POST ")
        or value.startswith("DELETE ")
    ):
        return True
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _check_balanced_delimiters(relative: str, text: str, failures: list[str]) -> None:
    stripped = _strip_comments_and_strings(text)
    pairs = {"}": "{", ")": "(", "]": "["}
    stack: list[tuple[str, int]] = []
    for index, char in enumerate(stripped):
        if char in pairs.values():
            stack.append((char, index))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                failures.append(f"{relative} has unbalanced delimiter {char!r} near offset {index}")
                return
            stack.pop()
    if stack:
        char, index = stack[-1]
        failures.append(f"{relative} has unclosed delimiter {char!r} near offset {index}")


def _strip_comments_and_strings(text: str) -> str:
    result: list[str] = []
    i = 0
    in_line_comment = False
    in_block_comment = False
    in_string: str | None = None
    escape = False
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            else:
                result.append(" ")
        elif in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                result.extend("  ")
                i += 1
            else:
                result.append("\n" if char == "\n" else " ")
        elif in_string:
            if escape:
                escape = False
                result.append(" ")
            elif char == "\\":
                escape = True
                result.append(" ")
            elif char == in_string:
                in_string = None
                result.append(" ")
            else:
                result.append("\n" if char == "\n" else " ")
        elif char == "/" and nxt == "/":
            in_line_comment = True
            result.extend("  ")
            i += 1
        elif char == "/" and nxt == "*":
            in_block_comment = True
            result.extend("  ")
            i += 1
        elif char in {'"', "'"}:
            in_string = char
            result.append(" ")
        else:
            result.append(char)
        i += 1
    return "".join(result)


def _check_no_secrets(path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append(f"{path.relative_to(ROOT)} appears to contain a secret-like token")


def _finish(failures: list[str]) -> int:
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Native review handoff check failed: {len(failures)} failure(s).")
        return 1
    print("Native review handoff check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
