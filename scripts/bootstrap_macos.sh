#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/mobile/ios/ThoughtPinsNative"
INSTALL_MISSING=false

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap_macos.sh [--install-missing]

Creates the Python virtual environment, installs deterministic frontend
dependencies, runs source gates, generates the Xcode project, and performs an
unsigned generic iOS Simulator build. Xcode itself and signing identities are
never installed or changed by this script.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --install-missing) INSTALL_MISSING=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bootstrap requires macOS. A Python virtual environment cannot provide Xcode or Apple signing." >&2
  exit 2
fi

if ! xcode-select -p >/dev/null 2>&1 || ! command -v xcodebuild >/dev/null 2>&1; then
  echo "Install and open Xcode, then select it with xcode-select before continuing." >&2
  exit 2
fi

if ! xcodebuild -checkFirstLaunchStatus >/dev/null 2>&1; then
  echo "Xcode first-launch components or license acceptance are incomplete." >&2
  echo "Open Xcode once, or run: sudo xcodebuild -runFirstLaunch" >&2
  exit 2
fi

install_brew_formula() {
  local formula="$1"
  if [[ "$INSTALL_MISSING" != true ]]; then
    echo "Missing $formula. Install it with Homebrew or rerun with --install-missing." >&2
    exit 2
  fi
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required for --install-missing. Install it from https://brew.sh first." >&2
    exit 2
  fi
  brew install "$formula"
}

if ! command -v xcodegen >/dev/null 2>&1; then
  install_brew_formula xcodegen
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  install_brew_formula node@22
  export PATH="$(brew --prefix node@22)/bin:$PATH"
fi

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  install_brew_formula python@3.13
  PYTHON_BIN="$(brew --prefix python@3.13)/bin/python3.13"
fi

echo "Xcode: $(xcodebuild -version | tr '\n' ' ')"
echo "XcodeGen: $(xcodegen --version)"
echo "Python: $($PYTHON_BIN --version)"
echo "Node: $(node --version)"

"$PYTHON_BIN" -m venv "$ROOT/.venv"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "$ROOT[dev]"

npm --prefix "$ROOT/frontend" ci
npm --prefix "$ROOT/frontend" run build

cd "$ROOT"
python scripts/check_architecture_budget.py
python scripts/check_ios_submission_source.py
python scripts/check_native_review_handoff.py
python scripts/check_public_export.py

cd "$APP_DIR"
xcodegen generate
xcodebuild \
  -resolvePackageDependencies \
  -project ThoughtPins.xcodeproj \
  -scheme ThoughtPins
xcodebuild \
  -project ThoughtPins.xcodeproj \
  -scheme ThoughtPins \
  -configuration Debug \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  clean build

echo
echo "macOS bootstrap passed. No signing identity or App Store credential was created or changed."
echo "Next: docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md"
