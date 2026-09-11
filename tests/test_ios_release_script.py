"""Exercise release-shell argument handling without Xcode or signing material.

The native CI job also runs this with macOS's /bin/bash (3.2), where an empty
optional array fails under nounset even though newer Bash versions accept it.
The external tools are fixtures; actual build validation remains a separate gate.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(Path("/bin/bash").exists(), "requires a POSIX Bash host")
class IOSReleaseScriptTests(unittest.TestCase):
    def test_release_modes_preserve_optional_google_arguments(self) -> None:
        for mode in ("preflight", "archive"):
            for google in (False, True):
                with self.subTest(mode=mode, google=google), tempfile.TemporaryDirectory() as directory:
                    self._check_invocation(Path(directory), mode=mode, google=google)

    def _check_invocation(self, root: Path, *, mode: str, google: bool) -> None:
        scripts = root / "scripts"
        scripts.mkdir()
        script = scripts / "ios_release.sh"
        shutil.copy2(ROOT / "scripts" / "ios_release.sh", script)
        app = root / "mobile" / "ios" / "ThoughtPinsNative"
        (app / "Resources").mkdir(parents=True)
        (app / "Resources" / "Info.plist").write_text("GOOGLE_IOS_REVERSED_CLIENT_ID\n", encoding="utf-8")
        commands = root / "commands"
        commands.mkdir()
        log = root / "calls.jsonl"
        fixture = (
            f"#!{sys.executable}\n"
            + """import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ["THOUGHTPINS_RELEASE_CALLS"], "a") as stream:
    stream.write(json.dumps([name, *sys.argv[1:]]) + "\\n")
if name == "uname":
    print("Darwin")
if name == "xcodebuild" and "-archivePath" in sys.argv:
    archive = pathlib.Path(sys.argv[sys.argv.index("-archivePath") + 1])
    (archive / "Products/Applications/Thought Pins.app").mkdir(parents=True)
"""
        )
        for name in ("uname", "xcodegen", "xcodebuild", "xcrun", "codesign", "python3"):
            path = commands / name
            path.write_text(fixture, encoding="utf-8")
            path.chmod(0o755)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("APPLE_", "GOOGLE_IOS_", "IOS_", "BASH_ENV"))
        }
        env.update(
            PATH=str(commands) + os.pathsep + os.defpath,
            THOUGHTPINS_RELEASE_CALLS=str(log),
            APPLE_TEAM_ID="TESTTEAM01",
            IOS_BUILD_NUMBER="42",
        )
        google_settings = {
            "GOOGLE_IOS_CLIENT_ID": "fixture.apps.googleusercontent.com",
            "GOOGLE_IOS_SERVER_CLIENT_ID": "fixture-web.apps.googleusercontent.com",
            "GOOGLE_IOS_REVERSED_CLIENT_ID": "com.googleusercontent.apps.fixture",
        }
        if google:
            env.update(google_settings)
        result = subprocess.run(["/bin/bash", str(script), mode], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        builds = [call for call in calls if call[0] == "xcodebuild" and "-resolvePackageDependencies" not in call]
        self.assertEqual(len(builds), 1 if mode == "preflight" else 2)
        expected = {f"{key}={value}" for key, value in google_settings.items()} if google else set()
        for build in builds:
            self.assertNotIn("", build, "An absent optional setting must not become an empty argument.")
            self.assertEqual({arg for arg in build if arg.startswith("GOOGLE_IOS_")}, expected)
            self.assertIn("CURRENT_PROJECT_VERSION=42", build)
        if mode == "archive":
            self.assertTrue(any(call[:2] == ["codesign", "--verify"] for call in calls))
