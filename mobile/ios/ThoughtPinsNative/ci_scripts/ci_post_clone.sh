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
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> ci_post_clone: preparing $PROJECT_DIR"
echo "    working directory: $(pwd)"
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

# ------------------------------------------------------------ build number
#
# CFBundleVersion has to be unique and increasing for every upload, and
# project.yml pins CURRENT_PROJECT_VERSION to 1 as a safe floor for a bare
# `xcodegen generate`. Xcode Cloud's own CI_BUILD_NUMBER is monotonic per
# workflow, which is exactly the property App Store Connect requires, so it wins
# here. Substituted into project.yml *before* generating, so the number is baked
# into the generated project rather than needing a build-setting override that
# the archive action might not carry.
#
# `manageAppVersionAndBuildNumber` is false in ExportOptions.plist, so whatever
# is set here is what App Store Connect receives.

if [ -n "${CI_BUILD_NUMBER:-}" ]; then
    echo "==> setting CURRENT_PROJECT_VERSION to $CI_BUILD_NUMBER"
    /usr/bin/sed -i.bak \
        "s/^    CURRENT_PROJECT_VERSION: .*/    CURRENT_PROJECT_VERSION: $CI_BUILD_NUMBER/" \
        "$PROJECT_DIR/project.yml"
    rm -f "$PROJECT_DIR/project.yml.bak"
    grep "CURRENT_PROJECT_VERSION" "$PROJECT_DIR/project.yml"
else
    echo "==> CI_BUILD_NUMBER is unset; leaving CURRENT_PROJECT_VERSION alone."
    echo "    That is expected when running this script by hand, and would be a"
    echo "    problem on a real Xcode Cloud build -- two uploads would collide."
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

echo "==> ci_post_clone: done"
echo "    project: $PROJECT_DIR/ThoughtPins.xcodeproj"
echo "    scheme:  ThoughtPins (shared)"
