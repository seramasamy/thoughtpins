from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_store_submission_packet_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_store_submission_packet.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Store submission packet check passed." in result.stdout


def _checker_module():
    path = ROOT / "scripts" / "check_store_submission_packet.py"
    spec = importlib.util.spec_from_file_location("check_store_submission_packet", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_store_submission_packet_rejects_stale_policy_sources() -> None:
    mod = _checker_module()
    refs = {key: f"https://example.com/{key}" for key in mod.REQUIRED_OFFICIAL_REFERENCES}
    failures: list[str] = []

    mod._check_policy_source_freshness(
        {"last_reviewed": "2026-01-01", "official_references": refs},
        {"sources_checked_on": "2026-01-01", "official_references": refs},
        {"last_reviewed": "2026-01-01", "official_references": refs},
        failures,
        today=date(2026, 7, 1),
    )

    assert any("stale" in failure for failure in failures)


def test_store_submission_packet_rejects_reference_drift() -> None:
    mod = _checker_module()
    refs = {key: f"https://example.com/{key}" for key in mod.REQUIRED_OFFICIAL_REFERENCES}
    inventory_refs = dict(refs)
    inventory_refs["google_data_safety_form"] = "https://example.com/outdated"
    failures: list[str] = []

    mod._check_policy_source_freshness(
        {"last_reviewed": "2026-07-01", "official_references": refs},
        {"sources_checked_on": "2026-07-01", "official_references": refs},
        {"last_reviewed": "2026-07-01", "official_references": inventory_refs},
        failures,
        today=date(2026, 7, 1),
    )

    assert any("data-safety inventory official reference google_data_safety_form" in failure for failure in failures)
