from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _cleanup_module():
    path = ROOT / "scripts" / "clean_local_artifacts.py"
    spec = importlib.util.spec_from_file_location("clean_local_artifacts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cleanup_plans_generated_runtime_artifacts_when_requested(tmp_path: Path) -> None:
    mod = _cleanup_module()
    for rel in (
        "vault/user/Vault Home.md",
        "data/thoughtpins.sqlite3",
        "logs/app.log",
        "pytest-cache-files-abc/cache",
        "write_probe_123/probe.txt",
        ".tmp/frontend-resolver-abc/out.json",
        ".tmp/eval-qdrant/index.bin",
        ".mypy_cache/3.13/cache.json",
        "scripts/__pycache__/tool.cpython-313.pyc",
        "src/thoughtpins/__pycache__/api.cpython-313.pyc",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated", encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "reports").mkdir()

    planned = {
        item.path.relative_to(tmp_path).as_posix() for item in mod.plan_cleanup(tmp_path, include_runtime_state=True)
    }

    assert "vault" in planned
    assert "data" in planned
    assert "logs" in planned
    assert "pytest-cache-files-abc" in planned
    assert "write_probe_123" in planned
    assert ".tmp/frontend-resolver-abc" in planned
    assert ".tmp/eval-qdrant" in planned
    assert ".mypy_cache" in planned
    assert "scripts/__pycache__" in planned
    assert "src/thoughtpins/__pycache__" in planned
    assert "src" not in planned
    assert "reports" not in planned


def test_cleanup_preserves_runtime_state_by_default(tmp_path: Path) -> None:
    mod = _cleanup_module()
    for rel in ("vault/user/note.md", "data/thoughtpins.sqlite3", "logs/app.log", "backups/local.zip"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime", encoding="utf-8")

    planned = {item.path.relative_to(tmp_path).as_posix() for item in mod.plan_cleanup(tmp_path)}

    assert planned == set()


def test_cleanup_apply_deletes_only_planned_artifacts(tmp_path: Path) -> None:
    mod = _cleanup_module()
    generated = tmp_path / "vault" / "user" / "note.md"
    generated.parent.mkdir(parents=True)
    generated.write_text("synthetic", encoding="utf-8")
    source = tmp_path / "src" / "thoughtpins" / "keep.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('keep')\n", encoding="utf-8")

    assert mod.main(tmp_path, ["--apply", "--include-runtime-state"]) == 0

    assert not (tmp_path / "vault").exists()
    assert source.exists()


def test_cleanup_optional_report_and_build_flags(tmp_path: Path) -> None:
    mod = _cleanup_module()
    for rel in ("reports/evidence.json", "frontend/dist/app.js", "htmlcov/index.html"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated", encoding="utf-8")

    default_planned = {item.path.relative_to(tmp_path).as_posix() for item in mod.plan_cleanup(tmp_path)}
    full_planned = {
        item.path.relative_to(tmp_path).as_posix()
        for item in mod.plan_cleanup(tmp_path, include_reports=True, include_build=True)
    }

    assert "reports" not in default_planned
    assert "frontend/dist" not in default_planned
    assert "htmlcov" not in default_planned
    assert {"reports", "frontend/dist", "htmlcov"}.issubset(full_planned)
