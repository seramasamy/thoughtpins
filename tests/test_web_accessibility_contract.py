from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker_module():
    path = ROOT / "scripts" / "check_web_accessibility_contract.py"
    spec = importlib.util.spec_from_file_location("check_web_accessibility_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_accessibility_contract_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_web_accessibility_contract.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Web accessibility contract check passed." in result.stdout


def test_accessibility_checker_rejects_unlabeled_icon_buttons(tmp_path: Path) -> None:
    mod = _checker_module()
    root = tmp_path / "src"
    root.mkdir()
    (root / "Bad.tsx").write_text("<IconButton><X /></IconButton>", encoding="utf-8")
    failures: list[str] = []

    mod._check_icon_button_labels(root, failures)

    assert any("IconButton must include aria-label and title" in failure for failure in failures)


def test_accessibility_checker_rejects_missing_live_region() -> None:
    mod = _checker_module()
    failures: list[str] = []

    mod._check_live_regions("", "", "", "", failures)

    assert any("React chat thread" in failure for failure in failures)
