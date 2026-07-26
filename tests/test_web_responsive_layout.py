from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker_module():
    path = ROOT / "scripts" / "check_web_responsive_layout.py"
    spec = importlib.util.spec_from_file_location("check_web_responsive_layout", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_responsive_layout_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_web_responsive_layout.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Web responsive layout check passed." in result.stdout


def test_responsive_checker_rejects_phone_only_maintenance_banner() -> None:
    mod = _checker_module()
    css = "@media (max-width: 640px) { .maintenance-banner { min-height: 44px; } }"
    failures: list[str] = []

    mod._check_maintenance_banner_once(css, failures)

    assert any("phone-only" in failure for failure in failures)
