from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker_module():
    path = ROOT / "scripts" / "app_store_compliance_check.py"
    spec = importlib.util.spec_from_file_location("app_store_compliance_check", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_store_compliance_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/app_store_compliance_check.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "App store compliance check passed" in result.stdout


def test_app_store_compliance_rejects_visible_founder_copy(tmp_path: Path) -> None:
    mod = _checker_module()
    public_ui = tmp_path / "app.js"
    public_ui.write_text("<h2>Founder Telegram Test</h2>", encoding="utf-8")
    failures: list[str] = []

    mod._check_public_ui_no_founder_copy([public_ui], failures)

    assert any("Founder Telegram Test" in failure for failure in failures)


def test_app_store_compliance_allows_internal_founder_config_keys(tmp_path: Path) -> None:
    mod = _checker_module()
    public_ui = tmp_path / "app.js"
    public_ui.write_text("const config = { founder_test_mode_enabled: false };", encoding="utf-8")
    failures: list[str] = []

    mod._check_public_ui_no_founder_copy([public_ui], failures)

    assert failures == []


def test_app_store_compliance_rejects_founder_testing_copy(tmp_path: Path) -> None:
    mod = _checker_module()
    public_route = tmp_path / "public.py"
    public_route.write_text('fallback = "local founder testing support copy"', encoding="utf-8")
    failures: list[str] = []

    mod._check_public_ui_no_founder_copy([public_route], failures)

    assert any("local founder testing" in failure for failure in failures)
