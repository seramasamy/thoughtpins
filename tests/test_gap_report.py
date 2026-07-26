from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _gap_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_gap_report.py"
    spec = importlib.util.spec_from_file_location("generate_gap_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gap_summary_separates_code_infra_and_deferred_checks() -> None:
    mod = _gap_module()
    evidence = {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "passed": True,
        "release_evidence_complete": False,
        "steps": [
            {"name": "release gate", "status": "passed", "seconds": 1.0, "command": []},
            {
                "name": "docker daemon availability",
                "status": "blocked",
                "seconds": 0.1,
                "command": [],
                "reason": "docker unavailable",
            },
            {
                "name": "playwright web smoke",
                "status": "blocked",
                "seconds": 0.1,
                "command": [],
                "reason": "spawn eperm",
            },
            {
                "name": "live article provider smoke",
                "status": "skipped",
                "seconds": 0.0,
                "command": [],
                "reason": "not requested",
            },
        ],
    }

    summary = mod.build_gap_summary(evidence)

    assert summary["readiness"] == "code-ready pending infrastructure proof"
    assert summary["code_gaps"] == []
    assert [item["name"] for item in summary["infrastructure_blockers"]] == [
        "docker daemon availability",
        "playwright web smoke",
    ]
    assert summary["deferred_live_checks"][0]["name"] == "live article provider smoke"
    assert ".\\scripts\\run_compose_rehearsal.ps1" in summary["next_commands"]
    assert "cd frontend && npm run smoke:web" in summary["next_commands"]
    assert any("--strict-complete" in command for command in summary["next_commands"])


def test_gap_summary_marks_failed_steps_as_code_gaps() -> None:
    mod = _gap_module()
    evidence = {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "passed": False,
        "release_evidence_complete": False,
        "steps": [
            {"name": "release gate", "status": "failed", "seconds": 1.0, "command": [], "reason": "exit code 1"},
        ],
    }

    summary = mod.build_gap_summary(evidence)
    markdown = mod.render_markdown(summary)

    assert summary["readiness"] == "not release-ready: code gaps remain"
    assert summary["code_gaps"][0]["name"] == "release gate"
    assert "## Code Gaps" in markdown
    assert "release gate" in markdown


def test_gap_summary_redacts_secret_like_output() -> None:
    mod = _gap_module()
    evidence = {
        "app": "Thought Pins",
        "steps": [
            {
                "name": "custom smoke",
                "status": "failed",
                "seconds": 1.0,
                "command": ["python", "script.py", "sk-" + "A" * 32],
                "reason": "token " + "jina_" + "A" * 32,
            }
        ],
    }

    summary = mod.build_gap_summary(evidence)
    rendered = mod.render_markdown(summary)

    assert "sk-" + "A" * 32 not in str(summary)
    assert "jina_" + "A" * 32 not in rendered
    assert "<redacted>" in str(summary)
