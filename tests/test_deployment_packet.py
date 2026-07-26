from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_packet_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_deployment_packet.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Deployment packet check passed." in result.stdout
