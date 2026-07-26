from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_compose_load_rehearsal.py"
K6_SCRIPT = ROOT / "load" / "k6-multi-tenant-flow.js"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_compose_load_rehearsal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_multi_tenant_load_script_checks_isolation_and_rate_limits() -> None:
    text = K6_SCRIPT.read_text(encoding="utf-8")

    assert "LOAD_ACCOUNTS_JSON" in text
    assert "other tenant markers absent" in text
    assert "foreign probe job hidden" in text
    assert "http.expectedStatuses(404)" in text
    assert 'executor: "per-vu-iterations"' in text
    assert "deep health is healthy" in text
    assert "entry queued" in text
    assert "PAUSE_SECONDS" in text


def test_load_duration_is_strictly_bounded() -> None:
    module = _load_module()

    assert module._duration_seconds("20s") == 20
    assert module._duration_seconds("2m") == 120
    for value in ("0s", "4s", "11m"):
        with pytest.raises(ValueError):
            module._duration_seconds(value)


def test_summary_reader_extracts_release_metrics(tmp_path: Path) -> None:
    module = _load_module()
    summary = tmp_path / "summary.json"
    summary.write_text(
        '{"metrics":{"http_reqs":{"count":20},"iterations":{"count":5},'
        '"http_req_duration":{"p(95)":123.45,"max":456.7},'
        '"http_req_failed":{"value":0},"checks":{"passes":25,"fails":0}}}',
        encoding="utf-8",
    )

    assert module._read_summary(summary) == {
        "http_requests": 20,
        "iterations": 5,
        "p95_ms": 123.45,
        "max_ms": 456.7,
        "failed_rate": 0.0,
        "checks_passed": 25,
        "checks_failed": 0,
    }
