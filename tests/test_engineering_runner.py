from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "_thoughtpins_run_engineering_checks"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, ROOT / "scripts" / "run_engineering_checks.py")
assert SPEC and SPEC.loader
run_engineering_checks = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = run_engineering_checks
SPEC.loader.exec_module(run_engineering_checks)


def test_project_python_prefers_repository_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("THOUGHTPINS_PYTHON", raising=False)
    expected = tmp_path / ".venv" / "Scripts" / "python.exe"
    expected.parent.mkdir(parents=True)
    expected.touch()

    assert run_engineering_checks._project_python(tmp_path) == str(expected.resolve())


def test_project_python_honors_explicit_override(tmp_path: Path, monkeypatch) -> None:
    expected = tmp_path / "managed-python.exe"
    expected.touch()
    monkeypatch.setenv("THOUGHTPINS_PYTHON", str(expected))

    assert run_engineering_checks._project_python(tmp_path / "repo") == str(expected.resolve())
