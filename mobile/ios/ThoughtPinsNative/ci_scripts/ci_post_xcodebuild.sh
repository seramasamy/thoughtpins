#!/bin/sh
#
# Runs on Xcode Cloud after every xcodebuild action, and by hand against any
# .xcarchive. It asserts the things App Store Connect checks at upload, so a
# bad archive fails the build that produced it instead of failing days later
# in Transporter:
#
#   1. Built with Xcode 26 / the iOS 26 SDK. Since 2026-04-28 App Store
#      Connect refuses anything older, so every archive from a Xcode 15 Mac
#      is a local artifact, never an upload candidate.
#   2. CFBundleVersion matches CI_BUILD_NUMBER when Xcode Cloud provides one.
#   3. Top-level CFBundleIconName present (ITMS-90713 otherwise).
#   4. Assets.car present (the missing-resources bug class).
#   5. PrivacyInfo.xcprivacy at the bundle root.
#
# Local use:  ci_post_xcodebuild.sh /path/to/Something.xcarchive
# Cloud use:  no arguments; CI_ARCHIVE_PATH is set by Xcode Cloud for archive
#             actions. Build/test actions without an archive are skipped, not
#             failed, so the script is safe to leave in place for every action.

set -eu

archive="${1:-${CI_ARCHIVE_PATH:-}}"
if [ -z "$archive" ]; then
    echo "==> ci_post_xcodebuild: no archive in this action (CI_ARCHIVE_PATH unset); nothing to assert"
    exit 0
fi
if [ ! -d "$archive" ]; then
    echo "ci_post_xcodebuild FAILED: archive path does not exist: $archive" >&2
    exit 1
fi

app="$(find "$archive/Products/Applications" -maxdepth 1 -name '*.app' -print -quit 2>/dev/null || true)"
if [ -z "$app" ]; then
    echo "ci_post_xcodebuild FAILED: no .app inside $archive/Products/Applications" >&2
    exit 1
fi
plist="$app/Info.plist"
echo "==> ci_post_xcodebuild: asserting upload readiness of $app"

fail=0
say_fail() { echo "FAIL: $1" >&2; fail=1; }
say_ok()   { echo "  ok: $1"; }

read_key() { /usr/libexec/PlistBuddy -c "Print :$1" "$plist" 2>/dev/null || true; }

# --- 1a. Xcode version. DTXcode is e.g. 2600 for Xcode 26.0.
dt_xcode="$(read_key DTXcode)"
if [ -n "$dt_xcode" ] && [ "$dt_xcode" -ge 2600 ] 2>/dev/null; then
    say_ok "DTXcode $dt_xcode (>= 2600)"
else
    say_fail "DTXcode is '${dt_xcode:-<missing>}' — App Store Connect requires Xcode 26+ since 2026-04-28. This archive can never be uploaded."
fi

# --- 1b. SDK. DTSDKName is e.g. iphoneos26.0.
sdk="$(read_key DTSDKName)"
sdk_major="$(printf '%s' "$sdk" | sed -E 's/^iphoneos([0-9]+).*/\1/')"
if [ -n "$sdk_major" ] && [ "$sdk_major" -ge 26 ] 2>/dev/null; then
    say_ok "DTSDKName $sdk (iOS 26+ SDK)"
else
    say_fail "DTSDKName is '${sdk:-<missing>}' — must be iphoneos26.0 or later for upload."
fi

# --- 2. Build number matches Xcode Cloud's counter when it exists.
bundle_version="$(read_key CFBundleVersion)"
if [ -n "${CI_BUILD_NUMBER:-}" ]; then
    if [ "$bundle_version" = "$CI_BUILD_NUMBER" ]; then
        say_ok "CFBundleVersion $bundle_version == CI_BUILD_NUMBER"
    else
        say_fail "CFBundleVersion is '$bundle_version' but CI_BUILD_NUMBER is '$CI_BUILD_NUMBER' — ci_post_clone's stamp did not reach the binary."
    fi
else
    echo "  --  CFBundleVersion $bundle_version (no CI_BUILD_NUMBER to compare; local run)"
fi

# --- 3. Top-level icon name (ITMS-90713).
icon_name="$(read_key CFBundleIconName)"
if [ "$icon_name" = "AppIcon" ]; then
    say_ok "CFBundleIconName = AppIcon"
else
    say_fail "CFBundleIconName is '${icon_name:-<missing>}' — upload fails with ITMS-90713."
fi

# --- 4. Compiled asset catalog.
if [ -f "$app/Assets.car" ]; then
    say_ok "Assets.car present"
else
    say_fail "Assets.car missing — no icon, no brand colours; the resources bug class is back."
fi

# --- 5. Privacy manifest at the bundle root.
if [ -f "$app/PrivacyInfo.xcprivacy" ]; then
    say_ok "PrivacyInfo.xcprivacy at bundle root"
else
    say_fail "PrivacyInfo.xcprivacy missing from bundle root — privacy-manifest rejection at upload."
fi

if [ "$fail" -ne 0 ]; then
    echo "ci_post_xcodebuild FAILED: this archive would be refused or broken at upload. Fix before spending TestFlight time on it." >&2
    exit 1
fi
echo "==> ci_post_xcodebuild: all upload-readiness assertions passed"
