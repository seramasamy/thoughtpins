from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_export_archive_is_verified_and_excludes_local_state(tmp_path: Path) -> None:
    archive_path = tmp_path / "thoughtpins-public.zip"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_public_export.py",
            "--output",
            str(archive_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("PUBLIC_EXPORT_MANIFEST.json"))

    assert ".env" not in names
    assert "mobile/android/local.properties" not in names
    assert "frontend/public/assets/thought-pins-icon-1024.png" in names
    assert "mobile/ios/ThoughtPinsNative/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png" in names
    assert manifest["file_count"] == len(names) - 1
    assert all(not name.startswith(("data/", "vault/", "logs/", "reports/", "backups/")) for name in names)
