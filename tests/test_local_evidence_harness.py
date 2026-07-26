from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_harness():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "collect_local_closed_beta_evidence.py"
    spec = importlib.util.spec_from_file_location("collect_local_closed_beta_evidence", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_evidence_env_keeps_runtime_artifacts_in_scratch(tmp_path):
    harness = _load_harness()
    env = harness._child_env(tmp_path, 9876)

    assert env["DATABASE_URL"].startswith("sqlite:///")
    assert (tmp_path / "data").as_posix() in env["DATABASE_URL"]
    assert env["VAULT_PATH"] == str(tmp_path / "vault")
    assert env["REPORTS_PATH"] == str(tmp_path / "runtime-reports")
    assert env["BACKUPS_PATH"] == str(tmp_path / "backups")
    assert env["QDRANT_PATH"] == str(tmp_path / "qdrant")
    assert env["ENABLE_TELEGRAM_BOT"] == "false"
    assert env["THOUGHTPINS_RUNTIME_SMOKE_HTTP_TIMEOUT_SECONDS"] == "180"


def test_collector_env_allows_telegram_validation_to_use_real_config(tmp_path):
    harness = _load_harness()
    server_env = harness._child_env(tmp_path, 9877)
    collector_env = harness._collector_env(server_env)

    assert "ENABLE_TELEGRAM_BOT" not in collector_env
    assert collector_env["DATABASE_URL"] == server_env["DATABASE_URL"]
    assert collector_env["BACKUPS_PATH"] == server_env["BACKUPS_PATH"]
    assert collector_env["ENABLE_FOUNDER_MODE"] == "false"
