"""Validate the iOS review target without pretending Windows can run Xcode."""

from __future__ import annotations

import json
import plistlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "mobile" / "ios" / "ThoughtPinsNative"


def main() -> int:
    failures = _required_source_failures()
    if failures:
        return finish(failures)
    _check_project(failures)
    _check_info_plist(failures)
    _check_privacy_and_entitlements(failures)
    _check_icon(failures)
    _check_review_shell(failures)
    _check_core_client(failures)
    _check_google_and_release_wiring(failures)
    _check_brand_mark(failures)
    return finish(failures)


def _required_source_failures() -> list[str]:
    required = (
        TARGET / "project.yml",
        TARGET / "Sources" / "ThoughtPinsNativeApp.swift",
        TARGET / "Sources" / "GoogleOAuthTokenProvider.swift",
        TARGET / "Resources" / "Info.plist",
        TARGET / "Resources" / "PrivacyInfo.xcprivacy",
        TARGET / "Resources" / "ThoughtPins.entitlements",
        TARGET / "Resources" / "Assets.xcassets" / "AppIcon.appiconset" / "Contents.json",
        TARGET / "Resources" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-1024.png",
        TARGET / "Resources" / "Assets.xcassets" / "LaunchMark.imageset" / "LaunchMark.svg",
    )
    return [f"missing iOS submission source: {path.relative_to(ROOT)}" for path in required if not path.is_file()]


def _check_project(failures: list[str]) -> None:
    project = (TARGET / "project.yml").read_text(encoding="utf-8")
    require(project, "PRODUCT_BUNDLE_IDENTIFIER: com.thoughtpins.app", "canonical iOS bundle identifier", failures)
    require(project, 'TARGETED_DEVICE_FAMILY: "1,2"', "universal iPhone/iPad target", failures)
    require(project, "CODE_SIGN_ENTITLEMENTS: Resources/ThoughtPins.entitlements", "entitlements binding", failures)
    require(project, "SWIFT_STRICT_CONCURRENCY: complete", "strict Swift concurrency", failures)
    require(project, "exactVersion: 9.1.0", "pinned native Google sign-in dependency", failures)
    require(
        project,
        "THOUGHTPINS_API_BASE_URL: https://api.thoughtpins.com",
        "HTTPS iOS API build setting",
        failures,
    )
    for marker in ["GOOGLE_IOS_CLIENT_ID", "GOOGLE_IOS_SERVER_CLIENT_ID", "GOOGLE_IOS_REVERSED_CLIENT_ID"]:
        require(project, marker, f"iOS Google build setting {marker}", failures)


def _check_info_plist(failures: list[str]) -> None:
    info = load_plist(TARGET / "Resources" / "Info.plist", failures)
    if not info:
        return
    if info.get("CFBundleDisplayName") != "Thought Pins":
        failures.append("Info.plist display name must be Thought Pins")
    if str(info.get("THOUGHTPINS_API_BASE_URL") or "") != "$(THOUGHTPINS_API_BASE_URL)":
        failures.append("iOS API base URL must be supplied by the release build setting")
    if info.get("ITSAppUsesNonExemptEncryption") is not False:
        failures.append("Info.plist must declare the current export-compliance posture")
    if not str(info.get("NSMicrophoneUsageDescription") or "").strip():
        failures.append("Info.plist must explain the user-initiated voice-note microphone access")
    for key in ("GIDClientID", "GIDServerClientID"):
        if key not in info:
            failures.append(f"Info.plist must declare {key} as a release build setting")
    url_types = info.get("CFBundleURLTypes") or []
    if not any("$(GOOGLE_IOS_REVERSED_CLIENT_ID)" in (item.get("CFBundleURLSchemes") or []) for item in url_types):
        failures.append("Info.plist must bind the Google callback URL scheme to its release build setting")
    required_phone_orientations = {
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationLandscapeLeft",
        "UIInterfaceOrientationLandscapeRight",
    }
    phone_orientations = set(info.get("UISupportedInterfaceOrientations") or [])
    if not required_phone_orientations.issubset(phone_orientations):
        failures.append("iPhone target must support portrait and both landscape orientations")
    ipad_orientations = set(info.get("UISupportedInterfaceOrientations~ipad") or [])
    if not (required_phone_orientations | {"UIInterfaceOrientationPortraitUpsideDown"}).issubset(ipad_orientations):
        failures.append("iPad target must support all four interface orientations")


def _check_privacy_and_entitlements(failures: list[str]) -> None:
    privacy = load_plist(TARGET / "Resources" / "PrivacyInfo.xcprivacy", failures)
    if privacy:
        if privacy.get("NSPrivacyTracking") is not False:
            failures.append("privacy manifest must explicitly disable tracking")
        if privacy.get("NSPrivacyTrackingDomains") != []:
            failures.append("privacy manifest must not declare tracking domains")
        collected = privacy.get("NSPrivacyCollectedDataTypes")
        if not isinstance(collected, list) or not collected:
            failures.append("privacy manifest must declare collected app data")
        if not any(
            isinstance(item, dict) and item.get("NSPrivacyCollectedDataType") == "NSPrivacyCollectedDataTypeAudioData"
            for item in collected or []
        ):
            failures.append("privacy manifest must declare optional audio data used by voice notes")

    entitlements = load_plist(TARGET / "Resources" / "ThoughtPins.entitlements", failures)
    if entitlements and entitlements.get("com.apple.developer.applesignin") != ["Default"]:
        failures.append("Sign in with Apple entitlement is missing or malformed")


def _check_icon(failures: list[str]) -> None:
    icon_manifest = json.loads(
        (TARGET / "Resources" / "Assets.xcassets" / "AppIcon.appiconset" / "Contents.json").read_text(encoding="utf-8")
    )
    images = icon_manifest.get("images") or []
    if not any(item.get("filename") == "AppIcon-1024.png" and item.get("size") == "1024x1024" for item in images):
        failures.append("app icon catalog must reference the 1024x1024 marketing icon")
    check_png_icon(TARGET / "Resources" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-1024.png", failures)


def _check_review_shell(failures: list[str]) -> None:
    source_root = ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp"
    shell = "\n".join(path.read_text(encoding="utf-8") for path in sorted(source_root.glob("*.swift")))
    for marker in [
        "SignInWithAppleButton",
        "credential.authorizationCode",
        "authorizationCode: authorizationCode",
        "configureAppleSignInRequest",
        "request.nonce = nonce",
        "credential.state == expectedState",
        "aiProcessingConsentAccepted",
        "I understand and allow this processing.",
        "confirmationDialog(",
        "Thinking with your memory",
        "Use private memories",
        "Private memories stay out of replies.",
        "includePrivate: usePrivateMemories",
        ".submitLabel(.send)",
        "ThoughtPinsVoiceRecorder",
        "Record a voice note",
        "Open original",
    ]:
        require(shell, marker, f"iOS review flow marker {marker}", failures)
    for forbidden in ["access-control evasion", "rawVaultPath", "Vault note", "provider diagnostics"]:
        if forbidden.lower() in shell.lower():
            failures.append(f"iOS user interface exposes forbidden internal wording: {forbidden}")


def _check_core_client(failures: list[str]) -> None:
    core_root = ROOT / "mobile" / "ios" / "ThoughtPinsCore"
    core_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((core_root / "Sources").rglob("*.swift"))
    )
    for marker in [
        "URLSessionConfiguration.ephemeral",
        "reloadIgnoringLocalCacheData",
        "Cache-Control",
        "refreshTask",
        "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
    ]:
        require(core_source, marker, f"iOS client security marker {marker}", failures)
    package_manifest = (core_root / "Package.swift").read_text(encoding="utf-8")
    require(package_manifest, ".testTarget", "ThoughtPinsCore XCTest target", failures)
    require(
        (core_root / "Tests" / "ThoughtPinsCoreTests" / "APIClientTests.swift").read_text(encoding="utf-8"),
        "testLogoutClearsLocalSessionWhenServerIsUnavailable",
        "iOS credential cleanup regression test",
        failures,
    )
    for swift_file in (ROOT / "mobile" / "ios").rglob("*.swift"):
        lines = [line.strip() for line in swift_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines and lines[-1].startswith("@"):
            failures.append(f"dangling Swift attribute at end of {swift_file.relative_to(ROOT)}")


def _check_google_and_release_wiring(failures: list[str]) -> None:
    google_source = (TARGET / "Sources" / "GoogleOAuthTokenProvider.swift").read_text(encoding="utf-8")
    for marker in ["GIDSignIn.sharedInstance.signIn", "idToken?.tokenString", "handle(url)"]:
        require(google_source, marker, f"native Google sign-in marker {marker}", failures)

    release_script = (ROOT / "scripts" / "ios_release.sh").read_text(encoding="utf-8")
    for marker in [
        "scripts/render_ios_info_plist.py",
        'INFOPLIST_FILE="$RELEASE_INFO_PLIST"',
        'GOOGLE_IOS_CLIENT_ID="$GOOGLE_CLIENT_ID"',
        'GOOGLE_IOS_SERVER_CLIENT_ID="$GOOGLE_SERVER_CLIENT_ID"',
        'GOOGLE_IOS_REVERSED_CLIENT_ID="$GOOGLE_REVERSED_CLIENT_ID"',
    ]:
        require(release_script, marker, f"signed iOS OAuth release marker {marker}", failures)

    rendered_info_script = (ROOT / "scripts" / "render_ios_info_plist.py").read_text(encoding="utf-8")
    for marker in ["GIDClientID", "GIDServerClientID", "CFBundleURLTypes", "--google-enabled"]:
        require(rendered_info_script, marker, f"conditional iOS Info.plist marker {marker}", failures)


def _check_brand_mark(failures: list[str]) -> None:
    mark = (TARGET / "Resources" / "Assets.xcassets" / "LaunchMark.imageset" / "LaunchMark.svg").read_text(
        encoding="utf-8"
    )
    require(mark, "#e8612b", "canonical Thought Pins mark color", failures)
    require(mark, "M64 17C39.7 17 22 34.4 22 57.5", "integrated memory-pin silhouette", failures)
    require(mark, 'stroke-width="5.5"', "small-size-safe brain fold weight", failures)
    require(mark, 'd="M64 29v64"', "continuous brain and pin center spine", failures)
    canonical_mark = (ROOT / "site" / "assets" / "thought-pins-mark.svg").read_text(encoding="utf-8")
    if mark != canonical_mark:
        failures.append("iOS launch mark must exactly match the canonical Thought Pins SVG")


def load_plist(path: Path, failures: list[str]) -> dict:
    try:
        with path.open("rb") as handle:
            value = plistlib.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        failures.append(f"invalid plist {path.relative_to(ROOT)}: {exc}")
        return {}


def check_png_icon(path: Path, failures: list[str]) -> None:
    data = path.read_bytes()
    if len(data) < 26 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        failures.append("AppIcon-1024.png is not a valid PNG")
        return
    width, height = struct.unpack(">II", data[16:24])
    color_type = data[25]
    if (width, height) != (1024, 1024):
        failures.append(f"app icon must be 1024x1024, found {width}x{height}")
    if color_type not in {0, 2, 3}:
        failures.append("app icon must not contain an alpha channel")


def require(text: str, marker: str, label: str, failures: list[str]) -> None:
    if marker not in text:
        failures.append(f"missing {label}")


def finish(failures: list[str]) -> int:
    if failures:
        print("iOS submission source check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("iOS submission source check passed")
    print("Host boundary: Xcode archive, signing, simulator/device smoke tests, and App Store upload require macOS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
