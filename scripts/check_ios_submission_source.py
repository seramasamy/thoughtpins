"""Validate the iOS review target without pretending Windows can run Xcode."""

from __future__ import annotations

import hashlib
import json
import plistlib
import re
import struct
import subprocess
import sys
from collections import defaultdict
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
    _check_required_reason_apis(failures)
    _check_icon(failures)
    _check_launch_appearance(failures)
    _check_local_data_cleanup(failures)
    _check_review_shell(failures)
    _check_core_client(failures)
    _check_swift_key_decoding(failures)
    _check_google_and_release_wiring(failures)
    _check_brand_mark(failures)
    _check_screenshots(failures)
    _check_ci_scripts(failures)
    _check_no_remote_packages(failures)
    _check_project_format(failures)
    _check_project_spec_keys(failures)
    _check_accent_matches_brand(failures)
    return finish(failures)


# Xcode Cloud requires these beside the .xcodeproj, executable, with a shebang.
CI_SCRIPTS = {
    "ci_post_clone.sh": "generates ThoughtPins.xcodeproj, which is not in the repository",
    "ci_post_xcodebuild.sh": "asserts the archive is upload-ready (Xcode 26 SDK, icon, assets, privacy manifest)",
}


# XcodeGen project-format values this repository may use, and the pbxproj
# objectVersion each one writes.
#
# The ceiling is set by the only Mac the app is signed on, which runs Xcode
# 15.2. Anything above this and Xcode refuses to open the project at all --
# "the project is in a future Xcode project file format" -- which blocks the two
# jobs that can only be done in the GUI: Xcode Cloud onboarding, and selecting
# the signing team. xcodebuild reads newer formats happily, so nothing in CI
# notices; the failure only appears when a human opens the project.
ALLOWED_PROJECT_FORMATS = {
    "xcode14_0": 56,
    "xcode15_0": 60,
}
MAX_OBJECT_VERSION = 60


# XcodeGen's documented ProjectSpec keys, restricted to the levels this spec
# uses. Deliberately an allowlist rather than a denylist: the whole failure this
# guards against is a key that *looks* plausible and does nothing.
XCODEGEN_KEYS = {
    "root": {
        "name",
        "include",
        "options",
        "attributes",
        "configs",
        "configFiles",
        "settings",
        "settingGroups",
        "targets",
        "packages",
        "aggregateTargets",
        "schemes",
        "projectReferences",
        "fileGroups",
    },
    "options": {
        "projectFormat",
        "createIntermediateGroups",
        "deploymentTarget",
        "bundleIdPrefix",
        "minimumXcodeGenVersion",
        "settingPresets",
        "developmentLanguage",
        "usesTabs",
        "indentWidth",
        "tabWidth",
        "xcodeVersion",
        "groupSortPosition",
        "transitivelyLinkDependencies",
        "generateEmptyDirectories",
        "localPackagesGroup",
        "fileTypes",
        "preGenCommand",
        "postGenCommand",
        "useBaseInternationalization",
        "schemePathPrefix",
        "defaultConfig",
        "parallelizeBuild",
        "buildImplicitDependencies",
    },
    "target": {
        "type",
        "platform",
        "sources",
        "dependencies",
        "settings",
        "scheme",
        "configFiles",
        "info",
        "entitlements",
        "preBuildScripts",
        "postBuildScripts",
        "postCompileScripts",
        "attributes",
        "requiresObjCLinking",
        "onlyCopyFilesOnInstall",
        "productName",
        "transitivelyLinkDependencies",
        "directlyEmbedCarthageDependencies",
        "buildRules",
        "legacy",
        "deploymentTarget",
        "templates",
        "templateAttributes",
        "buildToolPlugins",
    },
    "source": {
        "path",
        "name",
        "group",
        "compilerFlags",
        "excludes",
        "includes",
        "type",
        "optional",
        "buildPhase",
        "headerVisibility",
        "createIntermediateGroups",
        "attributes",
        "resourceTags",
        "inferDestinationFiltersByPath",
        "destinationFilters",
    },
    "dependency": {
        "target",
        "framework",
        "carthage",
        "sdk",
        "package",
        "bundle",
        "product",
        "embed",
        "link",
        "codeSign",
        "removeHeaders",
        "weak",
        "platformFilter",
        "platforms",
        "destinationFilters",
        "copy",
        "implicit",
        "findFrameworks",
    },
    "scheme": {"build", "run", "test", "profile", "analyze", "archive", "management"},
}


def _check_accent_matches_brand(failures: list[str]) -> None:
    """AccentColor and ThoughtPinsTheme.brand are the same colour, twice.

    They have to be. An asset catalog cannot reference Swift, and
    `ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME` is what tints every control
    outside `ThoughtPinsMainShell` -- the sign-in, consent, invite and
    update-required screens, none of which sit under that shell's
    `.tint(ThoughtPinsTheme.brand)`.

    Until the asset catalog actually shipped, AccentColor was absent from the
    bundle and those screens rendered in system blue while the rest of the app
    was orange. Now that both exist, the risk is the opposite one: two
    definitions of the brand colour drifting apart, so the app is branded one
    colour before sign-in and another after.
    """
    catalog = TARGET / "Resources" / "Assets.xcassets" / "AccentColor.colorset" / "Contents.json"
    theme = ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp" / "ThoughtPinsTheme.swift"
    if not catalog.is_file() or not theme.is_file():
        failures.append("cannot compare AccentColor with ThoughtPinsTheme.brand: a file is missing")
        return

    try:
        colors = json.loads(catalog.read_text(encoding="utf-8"))["colors"]
    except Exception as exc:
        failures.append(f"unreadable AccentColor.colorset: {exc}")
        return

    accent: dict[str, tuple[float, ...]] = {}
    for entry in colors:
        components = (entry.get("color") or {}).get("components") or {}
        appearances = entry.get("appearances") or []
        mode = "dark" if any(a.get("value") == "dark" for a in appearances) else "light"
        try:
            accent[mode] = tuple(float(components[c]) for c in ("red", "green", "blue"))
        except Exception:
            continue

    match = re.search(
        r"static let brand = dynamic\(light: \(([\d.]+), ([\d.]+), ([\d.]+)\), "
        r"dark: \(([\d.]+), ([\d.]+), ([\d.]+)\)\)",
        theme.read_text(encoding="utf-8"),
    )
    if not match:
        failures.append("could not read ThoughtPinsTheme.brand; the accent comparison cannot run")
        return
    numbers = [float(g) for g in match.groups()]
    brand: dict[str, tuple[float, ...]] = {"light": tuple(numbers[0:3]), "dark": tuple(numbers[3:6])}

    for mode in ("light", "dark"):
        if mode not in accent:
            failures.append(f"AccentColor.colorset has no {mode} variant")
            continue
        if any(abs(a - b) > 0.01 for a, b in zip(accent[mode], brand[mode], strict=True)):
            failures.append(
                f"AccentColor {mode} {accent[mode]} does not match ThoughtPinsTheme.brand "
                f"{brand[mode]}. The screens before sign-in take the asset and everything "
                "after takes the Swift value, so the app would be two different oranges."
            )


def _check_project_spec_keys(failures: list[str]) -> None:
    """Every key in project.yml must be one XcodeGen actually reads.

    This is the check that would have caught the worst defect of the release.
    `resources:` is not an XcodeGen target key. It sat in this spec looking
    entirely reasonable, XcodeGen ignored it without a word, and every archive
    ever built shipped with no asset catalog, no app icon and no privacy
    manifest. The build succeeded, the plist validated, and nothing anywhere
    said otherwise.

    XcodeGen does not warn about keys it does not recognise, so a typo or an
    invented key is silent by design. An allowlist is the only way to notice.
    A key rejected here is either a mistake or a deliberate addition, and a
    deliberate addition should come with a line in this list.

    Also checks that every path the spec points at exists, because a path that
    does not is the same failure wearing different clothes.
    """
    import yaml  # imported lazily: this is the only check that needs it

    path = TARGET / "project.yml"
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - a malformed spec fails earlier
        failures.append(f"could not parse {path.relative_to(ROOT)}: {exc}")
        return

    def check(node: dict, allowed: set[str], where: str) -> None:
        for key in node:
            if key not in allowed:
                failures.append(
                    f"{path.relative_to(ROOT)}: '{key}' under {where} is not an XcodeGen key. "
                    "XcodeGen ignores keys it does not recognise without warning, so this "
                    "does nothing. Check Docs/ProjectSpec.md for the real name."
                )

    check(spec, XCODEGEN_KEYS["root"], "the project root")
    check(spec.get("options") or {}, XCODEGEN_KEYS["options"], "options")

    for name, target in (spec.get("targets") or {}).items():
        check(target, XCODEGEN_KEYS["target"], f"target {name}")
        for entry in target.get("sources") or []:
            if isinstance(entry, dict):
                check(entry, XCODEGEN_KEYS["source"], f"a sources entry of target {name}")
                source_path = entry.get("path")
            else:
                source_path = entry
            if source_path and not (TARGET / str(source_path)).exists():
                failures.append(
                    f"{path.relative_to(ROOT)}: target {name} lists sources path '{source_path}', which does not exist"
                )
        for entry in target.get("dependencies") or []:
            if isinstance(entry, dict):
                check(entry, XCODEGEN_KEYS["dependency"], f"a dependency of target {name}")
        for setting, value in ((target.get("settings") or {}).get("base") or {}).items():
            if setting in {"INFOPLIST_FILE", "CODE_SIGN_ENTITLEMENTS"} and not (TARGET / str(value)).exists():
                failures.append(
                    f"{path.relative_to(ROOT)}: target {name} sets {setting} to '{value}', which does not exist"
                )

    for name, scheme in (spec.get("schemes") or {}).items():
        check(scheme, XCODEGEN_KEYS["scheme"], f"scheme {name}")


def _check_project_format(failures: list[str]) -> None:
    """The generated project must open in Xcode 15.2, not merely build.

    XcodeGen defaults `projectFormat` to the newest Xcode it knows about --
    2.46.0 defaults to xcode16_0, which writes objectVersion 77. That default
    shipped here undetected because CI runs macos-latest and no local step ever
    opened the project.

    Checked against project.yml rather than the generated pbxproj, because the
    .xcodeproj is gitignored and this gate has to run on Linux too. When a
    generated project does happen to be present, its objectVersion is checked as
    well, so a change in XcodeGen's own format mapping is caught rather than
    assumed.
    """
    project = (TARGET / "project.yml").read_text(encoding="utf-8")
    declared = None
    for line in project.splitlines():
        stripped = line.strip()
        if stripped.startswith("projectFormat:"):
            declared = stripped.split(":", 1)[1].strip().strip("\"'")
            break

    if declared is None:
        failures.append(
            "project.yml sets no options.projectFormat, so XcodeGen uses its newest "
            "default. That project cannot be opened by Xcode 15.2, which is the only "
            "Mac this app is signed on, and signing and Xcode Cloud onboarding both "
            f"need the GUI. Set one of: {', '.join(sorted(ALLOWED_PROJECT_FORMATS))}."
        )
    elif declared not in ALLOWED_PROJECT_FORMATS:
        failures.append(
            f"options.projectFormat is {declared!r}, which Xcode 15.2 cannot open. "
            f"Allowed: {', '.join(sorted(ALLOWED_PROJECT_FORMATS))}."
        )

    generated = TARGET / "ThoughtPins.xcodeproj" / "project.pbxproj"
    if not generated.is_file():
        return
    for line in generated.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("objectVersion"):
            digits = "".join(ch for ch in stripped if ch.isdigit())
            if digits and int(digits) > MAX_OBJECT_VERSION:
                failures.append(
                    f"the generated project is objectVersion {digits}, above the {MAX_OBJECT_VERSION} "
                    "Xcode 15.2 can open. project.yml's projectFormat and XcodeGen's format "
                    "mapping have diverged; regenerate and re-check."
                )
            break


def _check_no_remote_packages(failures: list[str]) -> None:
    """The iOS build must not fetch anything over the network to resolve.

    Two reasons, and the second is the one that costs money.

    Reliability: package resolution happens on every clean build. A remote
    dependency means a GitHub or vendor outage on submission day is an outage
    for us, and there is no committed Package.resolved to fall back on.

    Cost: Xcode Cloud bills 25 compute hours a month. Resolution time is billed
    like everything else, and with a purely local graph it is close to zero.
    Removing GoogleSignIn earned that; this keeps it.

    A local `path:` dependency is fine -- it is a directory in this repository.
    """
    project = (TARGET / "project.yml").read_text(encoding="utf-8")
    for line in project.splitlines():
        stripped = line.strip()
        if stripped.startswith("url:"):
            failures.append(
                f"remote Swift package in project.yml ({stripped}). The iOS build resolves "
                "entirely from this repository; a remote package makes a clean build depend "
                "on someone else's uptime and adds billed resolution time to every "
                "Xcode Cloud run."
            )

    for manifest in sorted((ROOT / "mobile" / "ios").glob("*/Package.swift")):
        text = manifest.read_text(encoding="utf-8")
        if ".package(url:" in text:
            failures.append(f"remote Swift package in {manifest.relative_to(ROOT)}. Local `path:` dependencies only.")


def _check_ci_scripts(failures: list[str]) -> None:
    """A cloud build script that is not executable silently does the wrong thing.

    Apple: "Xcode Cloud respects the shebang if the file is executable. If you
    don't include a shebang as the first line of your custom script or forget to
    make the file executable, Xcode Cloud runs the script as `zsh $filename`."

    This is not hypothetical here. `scripts/prepare_ios_submission.sh` was
    committed as mode 100644 and its CI step could never have run; nothing
    noticed until someone read the workflow. The same mistake on a cloud runner
    fails on a machine nobody can log into, so it is asserted rather than
    remembered.

    Git only records one permission bit, so this checks the index rather than
    the working tree: a file can be executable locally and committed 644.
    """
    directory = TARGET / "ci_scripts"
    if not directory.is_dir():
        failures.append(
            "missing mobile/ios/ThoughtPinsNative/ci_scripts. Xcode Cloud looks for "
            "custom build scripts in a ci_scripts directory beside the Xcode project."
        )
        return

    try:
        listing = subprocess.run(
            ["git", "ls-files", "-s", "--", str(directory.relative_to(ROOT))],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:  # pragma: no cover - git is present everywhere this runs
        listing = ""
    modes = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            modes[Path(parts[3]).name] = parts[0]

    for name, why in CI_SCRIPTS.items():
        path = directory / name
        if not path.is_file():
            failures.append(f"missing ci_scripts/{name}: it {why}")
            continue
        first = path.read_text(encoding="utf-8").splitlines()[:1]
        if not first or not first[0].startswith("#!"):
            failures.append(f"ci_scripts/{name} has no shebang on its first line")
        mode = modes.get(name)
        if mode is None:
            failures.append(f"ci_scripts/{name} is not committed, so Xcode Cloud will never see it")
        elif mode != "100755":
            failures.append(
                f"ci_scripts/{name} is committed as mode {mode}, not 100755. "
                "Xcode Cloud will ignore the shebang and run it under zsh. "
                f"Fix with: git update-index --chmod=+x {path.relative_to(ROOT)}"
            )


SCREENSHOT_ROOT = ROOT / "apple-submission" / "screenshots"

# Filename -> the pixel size App Store Connect expects for that slot.
SCREENSHOT_SETS = {
    "iphone-1284x2778": (1284, 2778),
    "ipad-2048x2732": (2048, 2732),
}
SCREENSHOT_NAMES = ("02-chat", "03-people", "04-recap", "05-places", "06-pins", "07-account")


def _check_screenshots(failures: list[str]) -> None:
    """Every listing screenshot must be its own screen, at the right size.

    This exists because two of them were not. `ipad-2048x2732/07-account.png`
    was a byte-identical copy of `06-pins.png` -- same md5,
    fe3144cb3d5a4c6db3b4b8f2e69749f2 -- so the iPad set claimed to show the
    Account screen and showed the Pins screen twice. It survived a full
    reviewer pass and a screenshot recapture, because nothing compared the
    files to each other and a human eye slides over two similar-looking lists.

    Guideline 2.3.1 is about metadata that does not match the app. A duplicated
    screenshot is exactly that, and a machine catches it in milliseconds.
    """
    if not SCREENSHOT_ROOT.is_dir():
        failures.append("missing apple-submission/screenshots")
        return

    digests: dict[str, list[str]] = defaultdict(list)
    for folder, (want_w, want_h) in SCREENSHOT_SETS.items():
        directory = SCREENSHOT_ROOT / folder
        if not directory.is_dir():
            failures.append(f"missing screenshot set: apple-submission/screenshots/{folder}")
            continue
        for name in SCREENSHOT_NAMES:
            path = directory / f"{name}.png"
            if not path.is_file():
                failures.append(f"missing screenshot: {path.relative_to(ROOT)}")
                continue
            data = path.read_bytes()
            digests[hashlib.md5(data).hexdigest()].append(str(path.relative_to(ROOT)))
            size = _png_size(data)
            if size is None:
                failures.append(f"unreadable PNG: {path.relative_to(ROOT)}")
            elif size != (want_w, want_h):
                failures.append(
                    f"{path.relative_to(ROOT)} is {size[0]}x{size[1]}; the {folder} slot needs {want_w}x{want_h}"
                )

    for digest, paths in sorted(digests.items()):
        if len(paths) > 1:
            failures.append(
                f"identical screenshots claim to show different screens (md5 {digest}): {', '.join(sorted(paths))}"
            )


def _png_size(data: bytes) -> tuple[int, int] | None:
    """Width and height from the IHDR chunk, without an image library."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _required_source_failures() -> list[str]:
    required = (
        TARGET / "project.yml",
        TARGET / "Sources" / "ThoughtPinsNativeApp.swift",
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
    require(
        project,
        "THOUGHTPINS_API_BASE_URL: https://api.thoughtpins.com",
        "HTTPS iOS API build setting",
        failures,
    )
    # The GOOGLE_IOS_* build settings used to be required here. v1 does not ship
    # Google sign-in -- the app refuses to offer it without Sign in with Apple,
    # which is not configured -- so those settings fed placeholders that resolved
    # to empty strings, and an empty URL scheme in a built Info.plist is
    # malformed. They are gone, and _check_google_config_is_all_or_nothing below
    # is what now holds the line: present and real, or absent.


def _resolved_build_setting(name: str) -> str | None:
    """The value project.yml gives a build setting, or None if it sets none."""
    project = (TARGET / "project.yml").read_text(encoding="utf-8")
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.*)$", project, re.M)
    if not match:
        return None
    return match.group(1).strip().strip('"').strip("'")


def _check_google_config_is_all_or_nothing(info: dict, failures: list[str]) -> None:
    """Google keys must be absent, or present with a value that resolves.

    v1 shipped GIDClientID and GIDServerClientID as `$(GOOGLE_IOS_CLIENT_ID)`
    style placeholders whose build settings were empty strings, plus a
    CFBundleURLTypes entry whose only scheme was also empty. None of it
    described anything the binary did once Google sign-in was gated behind Sign
    in with Apple, and an empty URL scheme is malformed.

    So: declare them properly or not at all. Restoring Google means restoring
    the keys *and* the build settings together, which is what this enforces.
    """
    google_keys = [key for key in ("GIDClientID", "GIDServerClientID") if key in info]
    if not google_keys:
        return
    for key in google_keys:
        raw = str(info.get(key) or "")
        if not raw.strip():
            failures.append(f"Info.plist declares {key} with no value")
            continue
        placeholder = re.fullmatch(r"\$\((\w+)\)", raw.strip())
        if not placeholder:
            continue
        setting = placeholder.group(1)
        value = _resolved_build_setting(setting)
        if not value:
            failures.append(
                f"Info.plist binds {key} to $({setting}), which project.yml leaves empty. "
                "A built Info.plist would carry an empty Google client ID. Configure it or remove the key."
            )
    if len(google_keys) == 1:
        failures.append("Info.plist declares only one of GIDClientID / GIDServerClientID")


def _check_no_empty_url_schemes(info: dict, where: str, failures: list[str]) -> None:
    """No CFBundleURLTypes entry may carry an empty or unresolvable scheme."""
    for index, entry in enumerate(info.get("CFBundleURLTypes") or []):
        schemes = entry.get("CFBundleURLSchemes")
        if not schemes:
            failures.append(f"{where}: CFBundleURLTypes[{index}] declares no URL scheme")
            continue
        for scheme in schemes:
            text = str(scheme or "").strip()
            if not text:
                failures.append(f"{where}: CFBundleURLTypes[{index}] declares an empty URL scheme")
                continue
            placeholder = re.fullmatch(r"\$\((\w+)\)", text)
            if placeholder and not _resolved_build_setting(placeholder.group(1)):
                failures.append(
                    f"{where}: CFBundleURLTypes[{index}] scheme is $({placeholder.group(1)}), "
                    "which resolves to an empty string in a built app"
                )


def check_built_info_plist(app_path: Path) -> list[str]:
    """Validate a *built* app's Info.plist, where placeholders are resolved.

    The source checks reason about placeholders; this is the same rules applied
    to what actually ships. Called by the ios CI job after the archive.
    """
    failures: list[str] = []
    plist = app_path / "Info.plist"
    if not plist.is_file():
        return [f"no Info.plist in {app_path}"]
    info = load_plist(plist, failures)
    if not info:
        return failures
    _check_no_empty_url_schemes(info, str(plist), failures)
    for key in ("GIDClientID", "GIDServerClientID"):
        if key in info and not str(info.get(key) or "").strip():
            failures.append(f"{plist}: {key} is present but empty")

    # App Store Connect rejects an upload whose top-level CFBundleIconName is
    # missing: ITMS-90713. Xcode injects it from
    # ASSETCATALOG_COMPILER_APPICON_NAME only when it *generates* the
    # Info.plist, and GENERATE_INFOPLIST_FILE is NO here, so it has to be
    # stated in the source plist. actool separately writes nested copies under
    # CFBundleIcons, which is why this failure is invisible on a device -- the
    # icon appears, and only the upload is refused.
    if not str(info.get("CFBundleIconName") or "").strip():
        failures.append(
            f"{plist}: no top-level CFBundleIconName. App Store Connect rejects the "
            "upload as ITMS-90713. The nested CFBundleIcons entries actool writes are "
            "not a substitute."
        )

    # These were absent from every archive until 2026-08-27, because project.yml
    # declared them under a `resources:` key that XcodeGen does not have and
    # silently ignored. The generated project had no Copy Bundle Resources
    # phase at all, so the app shipped with no icon, no privacy manifest and a
    # launch screen pointing at assets that were not there. Nothing noticed,
    # because the archive still built and the plist still validated.
    for name, why in (
        ("Assets.car", "the compiled asset catalog: without it there is no app icon and no launch image"),
        ("PrivacyInfo.xcprivacy", "the privacy manifest Apple requires for the APIs this app uses"),
    ):
        if not (app_path / name).exists():
            failures.append(f"{app_path.name} contains no {name} -- {why}")

    return failures


def _check_info_plist(failures: list[str]) -> None:
    info = load_plist(TARGET / "Resources" / "Info.plist", failures)
    if info and str(info.get("CFBundleIconName") or "").strip() != "AppIcon":
        # Also asserted on the built app, but this runs on Linux in the python
        # job, so the failure is caught on every push rather than only when the
        # macOS archive job runs.
        failures.append(
            "Resources/Info.plist must set CFBundleIconName to AppIcon. Xcode only "
            "injects it when it generates the Info.plist, and GENERATE_INFOPLIST_FILE "
            "is NO, so an upload without it is rejected as ITMS-90713."
        )
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
    _check_google_config_is_all_or_nothing(info, failures)
    _check_no_empty_url_schemes(info, "Info.plist", failures)
    # iPhone is portrait only, deliberately. The app is a single reading and
    # writing column -- chat transcript over a composer, and Forms -- with no
    # landscape-specific layout anywhere, and landscape leaves 375pt of height
    # on the smallest supported phone, which the composer and the toggle above
    # it already fill at the accessibility text sizes. Declaring an orientation
    # nobody has looked at is how a reviewer finds a broken screen by rotating.
    # iPad keeps all four, where there is room and where multitasking expects it.
    phone_orientations = set(info.get("UISupportedInterfaceOrientations") or [])
    if phone_orientations != {"UIInterfaceOrientationPortrait"}:
        failures.append(
            "iPhone target must declare portrait only; add landscape back only "
            "with a landscape layout and a test that exercises it"
        )
    all_four = {
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationPortraitUpsideDown",
        "UIInterfaceOrientationLandscapeLeft",
        "UIInterfaceOrientationLandscapeRight",
    }
    ipad_orientations = set(info.get("UISupportedInterfaceOrientations~ipad") or [])
    if not all_four.issubset(ipad_orientations):
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
        declared_types = {item.get("NSPrivacyCollectedDataType") for item in collected or [] if isinstance(item, dict)}
        if "NSPrivacyCollectedDataTypeAudioData" not in declared_types:
            failures.append("privacy manifest must declare optional audio data used by voice notes")

        # The file importer accepts .image, and the upload provider reads the
        # chosen file's bytes and base64-encodes them for the server, so a photo
        # a person picks is transmitted. Apple has a distinct data type for that
        # and it is not covered by Other User Content.
        root_view = (
            ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp" / "ThoughtPinsReviewShell.swift"
        ).read_text(encoding="utf-8")
        if ".image" in root_view and "NSPrivacyCollectedDataTypePhotosorVideos" not in declared_types:
            failures.append(
                "the file importer accepts images, so the privacy manifest must declare "
                "NSPrivacyCollectedDataTypePhotosorVideos"
            )

        # Nothing in the app registers for push or calls registerDevice, so no
        # device identifier leaves the device. Declaring one would overstate
        # collection on the product page.
        app_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp").glob("*.swift")
            )
        ) + (TARGET / "Sources" / "ThoughtPinsNativeApp.swift").read_text(encoding="utf-8")
        collects_device_id = "registerForRemoteNotifications" in app_sources or "registerDevice(" in app_sources
        if not collects_device_id and "NSPrivacyCollectedDataTypeDeviceID" in declared_types:
            failures.append(
                "privacy manifest declares a device identifier the app never collects: "
                "nothing registers for push or calls registerDevice"
            )
        if collects_device_id and "NSPrivacyCollectedDataTypeDeviceID" not in declared_types:
            failures.append("the app now collects a device identifier, so the privacy manifest must declare it")

    entitlements = load_plist(TARGET / "Resources" / "ThoughtPins.entitlements", failures)
    if entitlements and entitlements.get("com.apple.developer.applesignin") != ["Default"]:
        failures.append("Sign in with Apple entitlement is missing or malformed")


def _check_required_reason_apis(failures: list[str]) -> None:
    """Tie the privacy manifest to what the Swift actually calls.

    Apple rejects the upload with ITMS-91053 when a required-reason API is used
    without a declaration, and the manifest shipped with an empty
    NSPrivacyAccessedAPITypes while the chat screen stored its voice disclosure
    in @AppStorage. Deriving the requirement from the source means adding the
    next such call fails here rather than in App Store Connect.
    """
    swift = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "mobile" / "ios").rglob("*.swift")))
    # Category -> (source markers that require it, accepted reason codes).
    required_reason_apis = {
        "NSPrivacyAccessedAPICategoryUserDefaults": (
            ("@AppStorage", "UserDefaults"),
            {"CA92.1", "1C8F.1", "C56D.1", "AC6B.1"},
        ),
        "NSPrivacyAccessedAPICategoryFileTimestamp": (
            (".creationDateKey", ".contentModificationDateKey", "modificationDate", "attributesOfItem"),
            {"DDA9.1", "C617.1", "3B52.1", "0A2A.1"},
        ),
        "NSPrivacyAccessedAPICategoryDiskSpace": (
            ("volumeAvailableCapacity", "systemFreeSize", "volumeTotalCapacity"),
            {"E174.1", "85F4.1", "7D9E.1", "B728.1"},
        ),
        "NSPrivacyAccessedAPICategorySystemBootTime": (
            ("systemUptime", "mach_absolute_time"),
            {"35F9.1", "8FFB.1", "3D61.1"},
        ),
    }

    privacy = load_plist(TARGET / "Resources" / "PrivacyInfo.xcprivacy", failures)
    declared = {
        entry.get("NSPrivacyAccessedAPIType"): set(entry.get("NSPrivacyAccessedAPITypeReasons") or [])
        for entry in (privacy.get("NSPrivacyAccessedAPITypes") or [])
        if isinstance(entry, dict)
    }

    for category, (markers, valid_reasons) in required_reason_apis.items():
        used = next((marker for marker in markers if marker in swift), None)
        if used and category not in declared:
            failures.append(f"privacy manifest must declare {category}; the app calls {used}")
        elif used and not declared[category] & valid_reasons:
            failures.append(f"{category} needs a documented reason code, one of {sorted(valid_reasons)}")
        elif not used and category in declared:
            failures.append(f"privacy manifest declares {category} but nothing in the app uses it")


def _check_launch_appearance(failures: list[str]) -> None:
    """The launch background needs both appearances.

    A single light value paints the full-screen launch surface near-white for
    the moment before a dark-mode app draws itself, which is a visible flash on
    every cold start.
    """
    colorset = TARGET / "Resources" / "Assets.xcassets" / "LaunchBackground.colorset" / "Contents.json"
    if not colorset.is_file():
        failures.append("missing LaunchBackground colorset")
        return
    entries = json.loads(colorset.read_text(encoding="utf-8")).get("colors") or []
    has_dark = any(
        any(
            appearance.get("appearance") == "luminosity" and appearance.get("value") == "dark"
            for appearance in (entry.get("appearances") or [])
        )
        for entry in entries
    )
    if not has_dark:
        failures.append("LaunchBackground must carry a dark appearance so cold launches do not flash light")


def _check_local_data_cleanup(failures: list[str]) -> None:
    """Sign-out and deletion must take the offline drafts with them.

    FileDraftStore is keyed by device, not by account, and syncQueuedDrafts
    uploads whatever it finds under the current session. A draft left behind by
    a deleted account is journal text the next account on the device posts as
    its own.
    """
    core = ROOT / "mobile" / "ios" / "ThoughtPinsCore"
    draft_store = (core / "Sources" / "ThoughtPinsCore" / "DraftStore.swift").read_text(encoding="utf-8")
    require(draft_store, "public func purge()", "FileDraftStore.purge", failures)

    # The model is split across files -- ThoughtPinsAppModel.swift plus
    # extensions -- to stay inside the architecture budget, so this reads the
    # whole app package rather than one file. Pinning the filename made a
    # legitimate extraction look like a deleted feature.
    app_sources = ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp"
    model = "\n".join(path.read_text(encoding="utf-8") for path in sorted(app_sources.glob("*.swift")))
    require(model, "drafts.purge()", "offline draft purge on session teardown", failures)
    for caller in ("public func logout()", "public func deleteAccount()"):
        if caller not in model:
            failures.append(f"missing {caller} in the iOS app model")
    if "clearLocalAccountState" not in model:
        failures.append("sign-out and account deletion must share one local-state teardown")

    # The closed-beta gate has to be visible in the app, not only enforced by
    # the server. Registration is open, so an account can exist before it may be
    # used; without a screen the shell rendered a signed-in app whose every
    # request came back 403, which a store reviewer reports as a broken build.
    shell = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources").rglob("*.swift"))
    )
    for marker, label in (
        ("ThoughtPinsInviteView", "iOS closed-beta gate screen"),
        ("redeemInvite", "iOS invite redemption"),
    ):
        require(shell, marker, label, failures)

    # The predicate has to be read where routing happens, not merely defined.
    # A check that only greps every source together passes while the screen is
    # orphaned and unreachable.
    root_view = (
        ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp" / "ThoughtPinsReviewShell.swift"
    ).read_text(encoding="utf-8")
    require(root_view, "isBlockedByInviteGate", "iOS invite gate routing predicate", failures)

    # Deletion must stay reachable from behind the gate: 5.1.1(v) wants it
    # findable in the app, and a blocked account never reaches the Account tab.
    #
    # Scoped to the gate view's own body. The first version searched everything
    # after the type name across all sources, so the Account screen's own
    # "Delete account" button satisfied it — a check that could not fail.
    #
    # It asks for the trigger and the call, not the label. "Delete account"
    # appears twice in this view — once on the button, once on the confirmation
    # dialog — so matching the label alone stayed green with the button deleted
    # and the dialog left stranded behind nothing that could open it.
    _, _, after_declaration = root_view.partition("struct ThoughtPinsInviteView")
    if not after_declaration:
        failures.append("iOS invite gate screen is not declared in ThoughtPinsReviewShell.swift")
    else:
        for marker, what in (
            ("showingDeleteConfirmation = true", "a control that opens the delete confirmation"),
            ("model.deleteAccount()", "a call to deleteAccount"),
        ):
            if marker not in after_declaration:
                failures.append(f"the iOS invite gate must offer account deletion: missing {what}")

    tests = core / "Tests" / "ThoughtPinsCoreTests" / "DraftStoreTests.swift"
    if not tests.is_file():
        failures.append("missing DraftStoreTests.swift covering the draft purge")
    else:
        require(
            tests.read_text(encoding="utf-8"),
            "testPurgeLeavesNothingForTheNextAccountToSync",
            "cross-account draft leak regression test",
            failures,
        )


def _check_icon(failures: list[str]) -> None:
    icon_manifest = json.loads(
        (TARGET / "Resources" / "Assets.xcassets" / "AppIcon.appiconset" / "Contents.json").read_text(encoding="utf-8")
    )
    images = icon_manifest.get("images") or []
    if not any(item.get("filename") == "AppIcon-1024.png" and item.get("size") == "1024x1024" for item in images):
        failures.append("app icon catalog must reference the 1024x1024 marketing icon")
    check_png_icon(TARGET / "Resources" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-1024.png", failures)


def _check_login_service_parity(shell: str, failures: list[str]) -> None:
    """Guideline 4.8: never offer Google without Sign in with Apple.

    An app that uses a third-party login service must also offer an option that
    limits collection to name and email *and* lets the person keep their email
    address private. Email-and-password sign-up fails the second half, so Sign
    in with Apple is the only qualifying alternative here, and Google shown
    without it is a rejection.

    Deciding this in the client rather than in server config is deliberate: a
    flag flipped during a review window must not be able to put the shipped
    binary out of compliance. This check exists so the coupling is not quietly
    removed later.
    """
    declaration = "private var googleSignInAvailable: Bool {"
    start = shell.find(declaration)
    if start == -1:
        failures.append("iOS auth view must derive googleSignInAvailable in one place")
        return
    body = shell[start : start + 600]
    end = body.find("}")
    body = body[:end] if end != -1 else body
    if "appleSignInAvailable" not in body:
        failures.append(
            "Guideline 4.8: googleSignInAvailable must require appleSignInAvailable, "
            "so Google is never offered without Sign in with Apple"
        )


def _check_review_shell(failures: list[str]) -> None:
    source_root = ROOT / "mobile" / "ios" / "ThoughtPinsApp" / "Sources" / "ThoughtPinsApp"
    shell = "\n".join(path.read_text(encoding="utf-8") for path in sorted(source_root.glob("*.swift")))
    _check_login_service_parity(shell, failures)
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


def _check_swift_key_decoding(failures: list[str]) -> None:
    """Two ways to map JSON keys, and using both cancels them out.

    ThoughtPinsAPIClient sets `keyDecodingStrategy = .convertFromSnakeCase`,
    which rewrites an incoming `access_token` to `accessToken` and then looks
    for a CodingKey spelled `accessToken`. A model that *also* declares
    `case accessToken = "access_token"` is asking for a key the strategy has
    already consumed, so decoding throws and the model can never be built.

    Four models carried such enums and every one was undecodable: email login,
    OAuth login, token refresh, client config, ingest and device registration
    would all have failed against the live backend. Nothing catches it until
    the code runs, which on iOS meant nothing caught it at all.

    Two rules, both cheap:

    1. No `CodingKeys` enum may coexist with the global strategy.
    2. No property may carry an acronym run like `userID` or `apiURL`.
       `convertFromSnakeCase` produces `userId` from `user_id` and can never
       produce `userID`, so such a property is undecodable for the same reason
       even without an enum.
    """
    core = ROOT / "mobile" / "ios" / "ThoughtPinsCore" / "Sources" / "ThoughtPinsCore"
    client = (core / "APIClient.swift").read_text(encoding="utf-8")
    if "convertFromSnakeCase" not in client:
        # The rules below only hold while the strategy is in force.
        return

    # Only types that actually decode. ClientVersionDecision is Equatable and
    # built locally, so its `storeURL` never meets a JSON key and is fine — an
    # unscoped version of this check failed on it, which would have taught the
    # next reader that the rule is noise.
    declaration = re.compile(r"^(?:public\s+)?(?:struct|final class|class)\s+(\w+)\s*(?::\s*([^{]+?))?\s*\{", re.M)

    for swift_file in sorted(core.glob("*.swift")):
        text = swift_file.read_text(encoding="utf-8")
        name = swift_file.name

        for match in declaration.finditer(text):
            type_name, conformances = match.group(1), (match.group(2) or "")
            if "Codable" not in conformances and "Decodable" not in conformances:
                continue
            end = text.find("\n}", match.end())
            body = text[match.end() : end if end != -1 else len(text)]

            # A CodingKeys enum with explicit raw values re-does what the
            # strategy already did, and the two cancel out. Without raw values
            # it only selects which properties participate, which is safe.
            if re.search(r"enum\s+CodingKeys[^{]*\{[^}]*=\s*\"", body, re.S):
                failures.append(
                    f"{name}: {type_name} declares CodingKeys with explicit raw values while the "
                    f"client uses convertFromSnakeCase; the two cancel out and it cannot decode"
                )

            for prop in re.findall(r"^\s*(?:public\s+)?(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", body, re.M):
                # Two consecutive capitals is the whole test. convertFromSnakeCase
                # turns `user_id` into `userId` — one capital, then lowercase — so
                # `userID` is unreachable. An earlier version used
                # `([A-Z][a-z0-9]*)*`, which matches `userID` happily because the
                # lowercase run may be empty, and so passed on the very bug it
                # was written to catch.
                if re.search(r"[A-Z]{2,}", prop):
                    failures.append(
                        f"{name}: {type_name}.{prop} contains an acronym run, which "
                        f"convertFromSnakeCase can never produce, so it cannot decode"
                    )


def _check_google_and_release_wiring(failures: list[str]) -> None:
    """The release script still knows how to build a Google-enabled archive.

    The SDK itself is gone from v1 -- the app refuses a third-party login
    without Sign in with Apple beside it (Guideline 4.8), which is not
    configured, so the button never rendered and the provider could only throw.
    Linking it meant shipping a third-party SDK, and its transitive graph, that
    no code path could reach; it was also the single reason a Swift 5.9
    toolchain could not build the app target.

    What is checked here is therefore the *other* half: `ios_release.sh` must
    still be able to render an Info.plist carrying real Google values, so
    turning the feature back on in 1.1 is a matter of restoring the package and
    the two Info.plist keys rather than rebuilding this plumbing. The provider
    itself is recoverable from git history.
    """
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
    # Colour types 4 and 6 carry an alpha channel outright. Type 3 (indexed)
    # does not, but a tRNS chunk gives its palette per-entry transparency, and
    # types 0 and 2 can use tRNS to mark one colour transparent. Apple rejects
    # the upload for any of them, so the chunk has to be checked as well as the
    # colour type -- the old check let an indexed PNG with tRNS straight
    # through.
    if color_type in {4, 6}:
        failures.append("app icon must not contain an alpha channel")
    elif color_type not in {0, 2, 3}:
        failures.append(f"app icon has an unexpected PNG colour type: {color_type}")
    if _png_has_chunk(data, b"tRNS"):
        failures.append("app icon must not carry transparency: it contains a tRNS chunk")


def _png_has_chunk(data: bytes, name: bytes) -> bool:
    """Walk the PNG chunk list rather than searching the whole file.

    A raw `name in data` would also match the bytes appearing inside compressed
    image data, which is a false positive waiting to happen.
    """
    position = 8
    while position + 8 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk = data[position + 4 : position + 8]
        if chunk == name:
            return True
        if chunk == b"IEND":
            return False
        position += 12 + length
    return False


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


def main_built_app(app_path: str) -> int:
    """`--built-app <path>`: check a built .app's Info.plist.

    The source checks reason about `$(...)` placeholders; this runs the same
    rules against what actually ships, after Xcode has resolved them.
    """
    failures = check_built_info_plist(Path(app_path))
    if failures:
        print("built iOS Info.plist check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"built iOS Info.plist check passed: {app_path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--built-app":
        sys.exit(main_built_app(sys.argv[2]))
    sys.exit(main())
