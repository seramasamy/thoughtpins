#!/bin/sh
#
# Xcode Cloud runs this immediately after cloning the repository, before it
# looks for anything to build.
#
# It exists because `ThoughtPins.xcodeproj` is not in the repository. The
# project is generated from `project.yml` by XcodeGen, and `.gitignore` keeps
# the generated copy out of source control so two machines cannot produce
# conflicting pbxproj diffs. A cloud runner clones the repository and finds no
# project at all unless this script makes one.
#
# Location, per Apple: "Custom build scripts reside in a directory named
# ci_scripts that's located in the same directory as your Xcode project or
# workspace, and Xcode Cloud runs your custom build scripts with this directory
# as the root directory."  So this file lives beside ThoughtPins.xcodeproj, and
# the project directory is one level up from where this runs.
#
# The shebang and the executable bit both matter: "Xcode Cloud respects the
# shebang if the file is executable. If you don't include a shebang as the first
# line of your custom script or forget to make the file executable, Xcode Cloud
# runs the script as `zsh $filename`, which -- depending on your script -- can
# cause a failing build."  scripts/check_ios_submission_source.py asserts the
# mode, because `prepare_ios_submission.sh` shipped as 100644 once and its CI
# step could never have run.
#
# There is no interactive debugging on a cloud runner, so this script is loud:
# every step announces itself and every failure explains what to do about it.

set -eu

XCODEGEN_VERSION="2.46.0"

# Resolved from this script's own location, never from the working directory.
# Apple runs custom build scripts with ci_scripts as the root directory, but
# GitHub Actions and a hand-run both use the repository root, and relying on
# either would make one of them silently wrong. `dirname "$0"` is the same
# answer everywhere.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STARTED_AT="$(date +%s)"

echo "==> ci_post_clone: preparing $PROJECT_DIR"
echo "    working directory: $(pwd)  (not used; paths derive from \$0)"
echo "    CI_BUILD_NUMBER:   ${CI_BUILD_NUMBER:-<unset>}"
echo "    CI_BRANCH:         ${CI_BRANCH:-<unset>}"
echo "    CI_XCODE_SCHEME:   ${CI_XCODE_SCHEME:-<unset>}"

# ---------------------------------------------------------------- XcodeGen
#
# Pinned to an exact release rather than `brew install xcodegen`, for two
# reasons: the version is deterministic, so the cloud produces the same project
# this Mac does; and it does not depend on Homebrew's state or on a formula
# moving. Homebrew is the documented fallback if the download is ever blocked.

install_dir="$HOME/.xcodegen-$XCODEGEN_VERSION"
xcodegen_bin="$install_dir/bin/xcodegen"

if [ ! -x "$xcodegen_bin" ]; then
    echo "==> installing XcodeGen $XCODEGEN_VERSION"
    tarball="$(mktemp -d)/xcodegen.zip"
    url="https://github.com/yonaskolb/XcodeGen/releases/download/$XCODEGEN_VERSION/xcodegen.zip"
    if curl -fsSL --retry 3 --retry-delay 2 -o "$tarball" "$url"; then
        mkdir -p "$install_dir"
        unzip -q -o "$tarball" -d "$install_dir"
        # The release archive unpacks to xcodegen/{bin,share}.
        if [ -x "$install_dir/xcodegen/bin/xcodegen" ]; then
            xcodegen_bin="$install_dir/xcodegen/bin/xcodegen"
        fi
        chmod +x "$xcodegen_bin" || true
    else
        echo "    release download failed; falling back to Homebrew"
        brew install xcodegen
        xcodegen_bin="$(command -v xcodegen)"
    fi
fi

if [ ! -x "$xcodegen_bin" ]; then
    echo "ci_post_clone FAILED: XcodeGen is not installed and neither the pinned" >&2
    echo "release download nor Homebrew produced a usable binary." >&2
    exit 1
fi
echo "    xcodegen: $("$xcodegen_bin" --version 2>&1 | head -1)"
# Machine-readable, so a caller that needs XcodeGen afterwards can find the
# binary without guessing the version-pinned directory. Xcode Cloud ignores
# this; GitHub Actions puts it on PATH for the steps that follow.
echo "XCODEGEN_BIN=$xcodegen_bin"

# ------------------------------------------------------------ build number
#
# CFBundleVersion has to be unique and increasing for every upload, and
# project.yml pins it to 1 as a safe floor for a bare `xcodegen generate`.
# Substituted here *before* generating, so the number is baked into the project
# rather than needing a build-setting override the archive action might not
# carry. `manageAppVersionAndBuildNumber` is false in ExportOptions.plist, so
# whatever is set here is what App Store Connect receives.
#
# Two sources, in order of authority:
#
#   1. CI_BUILD_NUMBER -- Xcode Cloud's own counter. Monotonic per workflow,
#      which is exactly what App Store Connect requires, so it wins.
#   2. The commit count -- what a local Mac and GitHub Actions have. The same
#      integer for a given commit on every machine, and it only ever grows.
#
# If neither is available the script does not guess: it leaves project.yml's
# floor of 1 in place and says so loudly, because a silently repeated build
# number is rejected at upload rather than at build time.
build_number="${CI_BUILD_NUMBER:-}"
build_number_source="CI_BUILD_NUMBER"

if [ -z "$build_number" ]; then
    build_number_source="commit count"
    build_number="$(git -C "$PROJECT_DIR" rev-list --count HEAD 2>/dev/null || true)"
fi

if [ -n "$build_number" ] && [ "$build_number" -gt 0 ] 2>/dev/null; then
    echo "==> CURRENT_PROJECT_VERSION := $build_number (from $build_number_source)"
    /usr/bin/sed -i.bak \
        "s/^    CURRENT_PROJECT_VERSION: .*/    CURRENT_PROJECT_VERSION: $build_number/" \
        "$PROJECT_DIR/project.yml"
    rm -f "$PROJECT_DIR/project.yml.bak"
    grep "CURRENT_PROJECT_VERSION" "$PROJECT_DIR/project.yml"
else
    echo "WARNING: no CI_BUILD_NUMBER and no usable git history, so the build" >&2
    echo "number stays at project.yml's floor. That is fine for a local build" >&2
    echo "and wrong for anything uploaded: App Store Connect rejects a repeated" >&2
    echo "CFBundleVersion." >&2
fi

# ------------------------------------------------------------- generate it
echo "==> generating ThoughtPins.xcodeproj"
cd "$PROJECT_DIR"
"$xcodegen_bin" generate --spec project.yml

# Fail here rather than letting xcodebuild fail later with a vaguer message.
if [ ! -d "$PROJECT_DIR/ThoughtPins.xcodeproj" ]; then
    echo "ci_post_clone FAILED: XcodeGen ran but produced no ThoughtPins.xcodeproj." >&2
    exit 1
fi

# Xcode Cloud can only build a *shared* scheme. XcodeGen writes shared schemes
# into xcshareddata; if that ever stops being true the cloud build fails with
# "scheme not found", which is a confusing message to debug from a PC.
scheme="$PROJECT_DIR/ThoughtPins.xcodeproj/xcshareddata/xcschemes/ThoughtPins.xcscheme"
if [ ! -f "$scheme" ]; then
    echo "ci_post_clone FAILED: no shared scheme at $scheme" >&2
    echo "Xcode Cloud can only build shared schemes. Check the 'schemes:' block" >&2
    echo "in project.yml." >&2
    exit 1
fi

# Printed because this runs on every Xcode Cloud build and its wall-clock time
# is billed against a 25-hour monthly allowance. If this number starts to grow,
# it is the first place to look.
echo "==> ci_post_clone: done in $(( $(date +%s) - STARTED_AT ))s"
echo "    project: $PROJECT_DIR/ThoughtPins.xcodeproj"
echo "    scheme:  ThoughtPins (shared)"
