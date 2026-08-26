#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/mobile/ios/ThoughtPinsNative"
PROJECT="$APP_DIR/ThoughtPins.xcodeproj"
SCHEME="ThoughtPins"
MODE="${1:-preflight}"
MARKETING_VERSION="${IOS_MARKETING_VERSION:-1.0.0}"
BUILD_NUMBER="${IOS_BUILD_NUMBER:-}"
BUNDLE_ID="${IOS_BUNDLE_ID:-com.thoughtpins.app}"
API_BASE_URL="${IOS_API_BASE_URL:-https://api.thoughtpins.com}"
TEAM_ID="${APPLE_TEAM_ID:-}"
GOOGLE_CLIENT_ID="${GOOGLE_IOS_CLIENT_ID:-}"
GOOGLE_SERVER_CLIENT_ID="${GOOGLE_IOS_SERVER_CLIENT_ID:-}"
GOOGLE_REVERSED_CLIENT_ID="${GOOGLE_IOS_REVERSED_CLIENT_ID:-}"
# CFBundleVersion has to be unique and increasing for every upload, and it was
# pinned to 1 in project.yml: the first TestFlight upload would work and the
# second would be rejected as a repeat build number, on the day we iterate
# fastest. The commit count is the same integer here and on a CI runner for a
# given commit, so neither host needs a shared counter and the number only ever
# grows. IOS_BUILD_NUMBER still wins, for a re-upload from an unchanged commit.
if [[ -z "$BUILD_NUMBER" && "$MODE" != "preflight" ]]; then
  BUILD_NUMBER="$(git -C "$ROOT" rev-list --count HEAD)"
  echo "IOS_BUILD_NUMBER not set; using the commit count: $BUILD_NUMBER"
fi
OUTPUT_ROOT="${IOS_RELEASE_OUTPUT_DIR:-$ROOT/build/ios-release/$MARKETING_VERSION-${BUILD_NUMBER:-preflight}}"
RELEASE_INFO_PLIST="$OUTPUT_ROOT/Info.release.plist"
ARCHIVE_PATH="$OUTPUT_ROOT/ThoughtPins.xcarchive"
EXPORT_PATH="$OUTPUT_ROOT/export"
EXPORT_OPTIONS="$OUTPUT_ROOT/ExportOptions.plist"
EVIDENCE_DIR="$ROOT/reports/ios-release/$MARKETING_VERSION-${BUILD_NUMBER:-preflight}"

usage() {
  cat <<'EOF'
Usage: ./scripts/ios_release.sh [preflight|archive|export]

Required for archive/export:
  APPLE_TEAM_ID          Apple Developer Team ID
  IOS_BUILD_NUMBER       Monotonically increasing integer

Optional, but all-or-none when Google sign-in is shipped:
  GOOGLE_IOS_CLIENT_ID   Native iOS OAuth client ID
  GOOGLE_IOS_SERVER_CLIENT_ID
                         Backend/web OAuth client ID used as the token audience
  GOOGLE_IOS_REVERSED_CLIENT_ID
                         Reversed native client ID callback scheme

Optional:
  IOS_MARKETING_VERSION  Default: 1.0.0
  IOS_BUNDLE_ID          Default: com.thoughtpins.app
  IOS_API_BASE_URL       Default: https://api.thoughtpins.com
  IOS_RELEASE_OUTPUT_DIR Override ignored build output directory

preflight performs unsigned checks. archive creates and verifies a signed
xcarchive. export also creates an App Store Connect distribution export. The
script never uploads and never reads signing keys from the repository.
EOF
}

case "$MODE" in
  preflight|archive|export) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "Unknown mode: $MODE" >&2; usage >&2; exit 2 ;;
esac

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "iOS release execution requires macOS and Xcode." >&2
  exit 2
fi

for command in xcodegen xcodebuild xcrun codesign python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required macOS tool: $command" >&2
    exit 2
  fi
done

if [[ ! "$MARKETING_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)?$ ]]; then
  echo "IOS_MARKETING_VERSION must be a semantic version, got: $MARKETING_VERSION" >&2
  exit 2
fi
if [[ ! "$API_BASE_URL" =~ ^https:// ]]; then
  echo "IOS_API_BASE_URL must be HTTPS." >&2
  exit 2
fi
if [[ "$BUNDLE_ID" != "com.thoughtpins.app" ]]; then
  echo "IOS_BUNDLE_ID must remain com.thoughtpins.app for the canonical App Store target." >&2
  exit 2
fi

google_values=("$GOOGLE_CLIENT_ID" "$GOOGLE_SERVER_CLIENT_ID" "$GOOGLE_REVERSED_CLIENT_ID")
google_configured=0
for value in "${google_values[@]}"; do
  if [[ -n "$value" ]]; then
    google_configured=$((google_configured + 1))
  fi
done
if [[ "$google_configured" != 0 && "$google_configured" != 3 ]]; then
  echo "Google iOS OAuth must be configured with all three GOOGLE_IOS_* values or none." >&2
  exit 2
fi
if [[ "$google_configured" == 3 ]]; then
  if [[ ! "$GOOGLE_CLIENT_ID" =~ ^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$ ]]; then
    echo "GOOGLE_IOS_CLIENT_ID has an invalid Google OAuth client ID format." >&2
    exit 2
  fi
  if [[ ! "$GOOGLE_SERVER_CLIENT_ID" =~ ^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$ ]]; then
    echo "GOOGLE_IOS_SERVER_CLIENT_ID has an invalid Google OAuth client ID format." >&2
    exit 2
  fi
  expected_reversed="com.googleusercontent.apps.${GOOGLE_CLIENT_ID%.apps.googleusercontent.com}"
  if [[ "$GOOGLE_REVERSED_CLIENT_ID" != "$expected_reversed" ]]; then
    echo "GOOGLE_IOS_REVERSED_CLIENT_ID does not match GOOGLE_IOS_CLIENT_ID." >&2
    exit 2
  fi
fi

if [[ "$MODE" != "preflight" ]]; then
  if [[ ! "$TEAM_ID" =~ ^[A-Z0-9]{10}$ ]]; then
    echo "APPLE_TEAM_ID must be the 10-character Apple Developer Team ID." >&2
    exit 2
  fi
  if [[ ! "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]]; then
    echo "IOS_BUILD_NUMBER must be a positive integer." >&2
    exit 2
  fi
fi

google_build_settings=()
if [[ "$google_configured" == 3 ]]; then
  # These build settings only do anything if Info.plist still references them.
  # v1 removed GIDClientID, GIDServerClientID and CFBundleURLTypes, because with
  # no values they resolved to empty strings and an empty URL scheme is
  # malformed. Passing real values now would be a silent no-op: the archive
  # would claim Google sign-in and ship without the client ID or the callback
  # scheme. Refuse instead, and say what to restore.
  info_plist="$ROOT/mobile/ios/ThoughtPinsNative/Resources/Info.plist"
  if ! grep -q "GOOGLE_IOS_REVERSED_CLIENT_ID" "$info_plist"; then
    echo "GOOGLE_IOS_* values were supplied, but Info.plist has no Google keys to fill." >&2
    echo "Restore GIDClientID, GIDServerClientID and the CFBundleURLTypes entry bound to" >&2
    echo "\$(GOOGLE_IOS_REVERSED_CLIENT_ID), and re-add the three build settings to project.yml." >&2
    echo "See apple-submission/AFTER_DEVELOPER_ACCOUNT.md, 'What v1 ships for sign-in'." >&2
    exit 2
  fi
  google_build_settings+=(
    GOOGLE_IOS_CLIENT_ID="$GOOGLE_CLIENT_ID"
    GOOGLE_IOS_SERVER_CLIENT_ID="$GOOGLE_SERVER_CLIENT_ID"
    GOOGLE_IOS_REVERSED_CLIENT_ID="$GOOGLE_REVERSED_CLIENT_ID"
  )
else
  echo "Google sign-in is intentionally absent from this build."
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

mkdir -p "$OUTPUT_ROOT" "$EVIDENCE_DIR"
cd "$ROOT"
render_info_args=(
  --source "$APP_DIR/Resources/Info.plist"
  --output "$RELEASE_INFO_PLIST"
)
if [[ "$google_configured" == 3 ]]; then
  render_info_args+=(--google-enabled)
fi
"$PYTHON" scripts/render_ios_info_plist.py "${render_info_args[@]}"
"$PYTHON" scripts/check_architecture_budget.py
"$PYTHON" scripts/check_ios_submission_source.py
"$PYTHON" scripts/check_native_review_handoff.py
"$PYTHON" scripts/check_store_submission_packet.py
"$PYTHON" scripts/forbidden_scan.py

cd "$APP_DIR"
xcodegen generate
xcodebuild \
  -resolvePackageDependencies \
  -project "$PROJECT" \
  -scheme "$SCHEME"
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration Release \
  -destination 'generic/platform=iOS Simulator' \
  MARKETING_VERSION="$MARKETING_VERSION" \
  CURRENT_PROJECT_VERSION="${BUILD_NUMBER:-1}" \
  INFOPLIST_FILE="$RELEASE_INFO_PLIST" \
  THOUGHTPINS_API_BASE_URL="$API_BASE_URL" \
  "${google_build_settings[@]}" \
  CODE_SIGNING_ALLOWED=NO \
  clean build | tee "$EVIDENCE_DIR/unsigned-build.log"

if [[ "$MODE" == "preflight" ]]; then
  echo "iOS release preflight passed. Archive signing was not requested."
  exit 0
fi

rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"
xcodebuild archive \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" \
  INFOPLIST_FILE="$RELEASE_INFO_PLIST" \
  THOUGHTPINS_API_BASE_URL="$API_BASE_URL" \
  "${google_build_settings[@]}" \
  MARKETING_VERSION="$MARKETING_VERSION" \
  CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
  CODE_SIGN_STYLE=Automatic \
  -allowProvisioningUpdates | tee "$EVIDENCE_DIR/archive.log"

APP_PATH="$ARCHIVE_PATH/Products/Applications/Thought Pins.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Signed archive is missing the expected app bundle: $APP_PATH" >&2
  exit 1
fi
codesign --verify --deep --strict --verbose=2 "$APP_PATH" 2>&1 | tee "$EVIDENCE_DIR/codesign-verify.log"
codesign -d --entitlements :- "$APP_PATH" > "$EVIDENCE_DIR/signed-entitlements.plist" 2> "$EVIDENCE_DIR/codesign-details.log"

if [[ "$MODE" == "archive" ]]; then
  echo "Signed archive created and verified: $ARCHIVE_PATH"
  echo "Inspect and validate it in Xcode Organizer before upload."
  exit 0
fi

python3 - "$EXPORT_OPTIONS" "$TEAM_ID" <<'PY'
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
team_id = sys.argv[2]
payload = {
    "destination": "export",
    "manageAppVersionAndBuildNumber": False,
    "method": "app-store-connect",
    "signingStyle": "automatic",
    "stripSwiftSymbols": True,
    "teamID": team_id,
    "uploadSymbols": True,
}
path.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True))
PY

xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$EXPORT_OPTIONS" \
  -allowProvisioningUpdates | tee "$EVIDENCE_DIR/export.log"

IPA_PATH="$(find "$EXPORT_PATH" -maxdepth 1 -name '*.ipa' -print -quit)"
if [[ -z "$IPA_PATH" || ! -f "$IPA_PATH" ]]; then
  echo "App Store export completed without producing an IPA." >&2
  exit 1
fi
shasum -a 256 "$IPA_PATH" > "$EVIDENCE_DIR/ipa-sha256.txt"

python3 - "$EVIDENCE_DIR/release-evidence.json" "$MARKETING_VERSION" "$BUILD_NUMBER" "$BUNDLE_ID" "$API_BASE_URL" "$TEAM_ID" "$IPA_PATH" <<'PY'
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

def output(*command: str) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        return "unavailable"

destination = Path(sys.argv[1])
payload = {
    "app": "Thought Pins",
    "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "marketing_version": sys.argv[2],
    "build_number": sys.argv[3],
    "bundle_id": sys.argv[4],
    "api_base_url": sys.argv[5],
    "team_id": sys.argv[6],
    "ipa_name": Path(sys.argv[7]).name,
    "macos": platform.mac_ver()[0],
    "xcode": output("xcodebuild", "-version"),
    "source_revision": output("git", "rev-parse", "HEAD"),
    "uploaded": False,
}
destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "Signed App Store export created: $IPA_PATH"
echo "SHA-256 and release evidence: $EVIDENCE_DIR"
echo "Upload only after Xcode Organizer validation and the device matrix pass."
