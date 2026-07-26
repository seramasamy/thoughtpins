from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_review_notes_packet_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_review_notes_packet.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Review notes packet check passed." in result.stdout
