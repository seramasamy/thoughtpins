from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker_module():
    path = ROOT / "scripts" / "check_workspace_hygiene.py"
    spec = importlib.util.spec_from_file_location("check_workspace_hygiene", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workspace_hygiene_check_passes_current_tree() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_workspace_hygiene.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Workspace hygiene check passed" in result.stdout


def test_workspace_hygiene_rejects_missing_ignore_marker(tmp_path: Path) -> None:
    mod = _checker_module()
    (tmp_path / ".gitignore").write_text(".tmp/\n", encoding="utf-8")
    (tmp_path / ".dockerignore").write_text(".tmp\n", encoding="utf-8")
    findings: list[str] = []

    mod.check_ignore_alignment(tmp_path, findings)

    assert any(".gitignore missing generated-artifact exclusion" in finding for finding in findings)
    assert any(".dockerignore missing generated-artifact exclusion" in finding for finding in findings)


def test_workspace_hygiene_flags_generated_manifest_paths() -> None:
    mod = _checker_module()

    assert mod._is_generated_public_path("reports/closed-beta.json") is True
    assert mod._is_generated_public_path("frontend/dist/app.js") is True
    assert mod._is_generated_public_path("src/thoughtpins.egg-info/SOURCES.txt") is True
    assert mod._is_generated_public_path("src/thoughtpins/vault/exporter.py") is False


def test_workspace_hygiene_matches_generated_root_prefixes() -> None:
    mod = _checker_module()
    patterns = {"pytest-cache-files-*/", "write_probe_*/", ".tmp/", "*.sqlite3"}

    assert mod._matches_ignore("pytest-cache-files-example", patterns) is True
    assert mod._matches_ignore("write_probe_abc123", patterns) is True
    assert mod._matches_ignore(".tmp", patterns) is True
    assert mod._matches_ignore("local.sqlite3", patterns) is True
    assert mod._matches_ignore("src", patterns) is False


def test_runtime_vault_ignore_is_root_scoped() -> None:
    gitignore = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
    dockerignore = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())

    assert "/vault/" in gitignore
    assert "vault/" not in gitignore
    assert "vault/**" in dockerignore
    assert "vault" not in dockerignore
