from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_postgres_dump_restore.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_postgres_dump_restore", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_restore_drill_rejects_unscoped_resources() -> None:
    module = _load_module()

    module.assert_safe_project("thoughtpins-recovery-proof")
    module.assert_safe_identifier("thoughtpins_app", label="role")

    for project in ("", "thoughtpins", "production", "thoughtpins_unsafe", "thoughtpins-Upper"):
        with pytest.raises(ValueError):
            module.assert_safe_project(project)
    for identifier in ("", "thoughtpins;drop", "name-with-dash", "two words"):
        with pytest.raises(ValueError):
            module.assert_safe_identifier(identifier, label="fixture")


def test_restore_drill_drop_guard_accepts_only_random_fixture_names() -> None:
    module = _load_module()

    assert module.SAFE_SCRATCH_DATABASE_RE.fullmatch("thoughtpins_restore_drill_012345abcdef")
    for database in ("thoughtpins", "postgres", "thoughtpins_restore_drill_", "thoughtpins_restore_drill_nothex"):
        assert not module.SAFE_SCRATCH_DATABASE_RE.fullmatch(database)


def test_wsl_compose_command_is_argument_safe() -> None:
    module = _load_module()

    if sys.platform == "win32":
        assert module._compose_command("Ubuntu-22.04", "thoughtpins-recovery-proof") == [
            "wsl.exe",
            "-d",
            "Ubuntu-22.04",
            "-u",
            "root",
            "--",
            "docker",
            "compose",
            "-p",
            "thoughtpins-recovery-proof",
        ]
        with pytest.raises(ValueError):
            module._compose_command("Ubuntu;rm", "thoughtpins-recovery-proof")
