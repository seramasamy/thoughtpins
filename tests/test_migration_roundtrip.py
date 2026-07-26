"""The disposable migration proof stays part of the local release gate."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_migration_roundtrip_script() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_migration_roundtrip.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Migration round-trip check passed" in result.stdout
