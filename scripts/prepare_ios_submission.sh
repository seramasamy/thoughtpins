#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/mobile/ios/ThoughtPinsNative"
DESTINATION="${THOUGHTPINS_IOS_DESTINATION:-generic/platform=iOS Simulator}"

for command in xcodegen xcodebuild; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required macOS tool: $command" >&2
    exit 2
  fi
done

cd "$APP_DIR"
xcodegen generate
xcodebuild -resolvePackageDependencies -project ThoughtPins.xcodeproj -scheme ThoughtPins
xcodebuild \
  -project ThoughtPins.xcodeproj \
  -scheme ThoughtPins \
  -destination "$DESTINATION" \
  CODE_SIGNING_ALLOWED=NO \
  clean build

echo "Unsigned iOS simulator build passed. Signing, archive validation, and device tests remain release-account work."
