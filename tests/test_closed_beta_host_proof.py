from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _proof_module():
    path = ROOT / "scripts" / "run_closed_beta_host_proof.py"
    spec = importlib.util.spec_from_file_location("run_closed_beta_host_proof", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_host_proof_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_closed_beta_host_proof.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "closed-beta host proof" in result.stdout
    assert "--project-name" in result.stdout
    assert "--no-strict-complete" in result.stdout


def test_host_proof_orchestrates_required_artifacts() -> None:
    source = (ROOT / "scripts" / "run_closed_beta_host_proof.py").read_text(encoding="utf-8-sig")

    for marker in (
        "compose-rehearsal-latest.json",
        "playwright-web-smoke.json",
        "web-smoke",
        "scripts/run_compose_rehearsal.py",
        "Docker daemon preflight",
        "strict host capability preflight",
        "--strict",
        "--with-browser-smoke",
        "scripts/check_external_proof_artifacts.py",
        "--require-both",
        "scripts/collect_local_closed_beta_evidence.py",
        "--strict-complete",
        "npm",
        "smoke:web",
        "install:playwright",
    ):
        assert marker in source


def test_host_proof_scopes_compose_project_names() -> None:
    mod = _proof_module()

    mod._assert_safe_project_name("thoughtpins-review-1")
    for bad in ("", "default", "thoughtpin", "thoughtpins_unsafe", "other-project"):
        try:
            mod._assert_safe_project_name(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe project accepted: {bad}")


def test_host_proof_reports_latest_evidence_bundle(monkeypatch, tmp_path, capsys) -> None:
    mod = _proof_module()
    old = tmp_path / "closed-beta-evidence-20260101T000000Z.json"
    latest = tmp_path / "closed-beta-evidence-20260102T000000Z.json"
    old.write_text(json.dumps({"report_path": "old-report"}), encoding="utf-8")
    latest.write_text(
        json.dumps(
            {
                "report_path": "reports/evidence.json",
                "gap_report_path": "reports/gap.md",
                "launch_packet_path": "reports/launch.md",
                "objective_audit_path": "reports/objective.md",
                "store_readiness_matrix_path": "reports/store.md",
            }
        ),
        encoding="utf-8",
    )
    os.utime(old, (1, 1))
    os.utime(latest, (2, 2))
    monkeypatch.setattr(mod, "REPORTS", tmp_path)

    mod._print_latest_evidence_bundle()

    output = capsys.readouterr().out
    assert "evidence bundle:" in output
    assert "reports/evidence.json" in output
    assert "objective audit: reports/objective.md" in output
    assert "store readiness matrix: reports/store.md" in output
    assert "old-report" not in output


def test_host_proof_redacts_secret_like_values() -> None:
    mod = _proof_module()
    fake_openai_key = "sk" + "-proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    text = f"postgresql+psycopg2://user:pass@localhost/db token {fake_openai_key} Bearer abc.def"

    redacted = mod._redact(text)

    assert "user:pass" not in redacted
    assert "sk-proj" not in redacted
    assert "abc.def" not in redacted
    assert "***" in redacted
