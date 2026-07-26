from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _collector_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "collect_closed_beta_evidence.py"
    spec = importlib.util.spec_from_file_location("collect_closed_beta_evidence", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_evidence_redaction_removes_provider_tokens_and_passwords():
    mod = _collector_module()
    raw = "\n".join(
        [
            "telegram=" + "1234567890" + ":" + "A" * 35,
            "llm_provider=" + "sk-" + "proj-" + "A" * 32,
            "jina=" + "jina_" + "A" * 32,
            "firecrawl=" + "fc-" + "A" * 32,
            "Authorization: Bearer abc.def.ghi",
            "API_KEY=super-secret-value",
            "DATABASE_URL=postgresql+psycopg2://owner:ownerpass@localhost/thoughtpins",
            "REDIS_URL=redis://:redispass@localhost:6379/0",
        ]
    )

    redacted = mod._redact(raw)

    for forbidden in [
        "1234567890:",
        "sk-proj-",
        "jina_A",
        "fc-A",
        "abc.def.ghi",
        "super-secret-value",
        "ownerpass",
        "redispass",
    ]:
        assert forbidden not in redacted
    assert "<redacted>" in redacted
    assert "postgresql+psycopg2://***:***@localhost/thoughtpins" in redacted
    assert "redis://:***@localhost:6379/0" in redacted


def test_evidence_classification_separates_blockers_from_failures():
    mod = _collector_module()

    assert mod._classify(0, "ok") == ("passed", "")
    assert mod._classify(1, "Error: spawn EPERM") == ("blocked", "spawn eperm")
    status, reason = mod._classify(1, "Cannot connect to the Docker daemon")
    assert status == "blocked"
    assert "docker daemon" in reason
    assert mod._classify(2, "assertion failed") == ("failed", "exit code 2")


def test_evidence_payload_marks_incomplete_when_blocked_or_skipped():
    mod = _collector_module()
    report = mod.EvidenceReport()
    report.steps.extend(
        [
            mod.EvidenceStep(name="release gate", status="passed", seconds=1.0, command=[]),
            mod.EvidenceStep(
                name="docker daemon availability",
                status="blocked",
                seconds=0.1,
                command=[],
                reason="docker unavailable",
            ),
            mod.EvidenceStep(
                name="playwright web smoke", status="skipped", seconds=0.0, command=[], reason="not requested"
            ),
        ]
    )

    payload = mod._report_payload(report)

    assert payload["passed"] is True
    assert payload["no_failed_steps"] is True
    assert payload["release_evidence_complete"] is False
    assert payload["blocked_steps"] == ["docker daemon availability"]
    assert payload["skipped_steps"] == ["playwright web smoke"]
    assert payload["failed_steps"] == []


def test_evidence_payload_marks_failed_step():
    mod = _collector_module()
    report = mod.EvidenceReport()
    report.steps.append(
        mod.EvidenceStep(name="release gate", status="failed", seconds=1.0, command=[], reason="exit code 1")
    )

    payload = mod._report_payload(report)

    assert payload["passed"] is False
    assert payload["no_failed_steps"] is False
    assert payload["release_evidence_complete"] is False
    assert payload["failed_steps"] == ["release gate"]


def test_evidence_exit_code_supports_strict_completeness():
    mod = _collector_module()
    complete = mod.EvidenceReport()
    complete.steps.append(mod.EvidenceStep(name="release gate", status="passed", seconds=1.0, command=[]))
    assert mod._exit_code(complete, strict_complete=False) == 0
    assert mod._exit_code(complete, strict_complete=True) == 0

    incomplete = mod.EvidenceReport()
    incomplete.steps.extend(
        [
            mod.EvidenceStep(name="release gate", status="passed", seconds=1.0, command=[]),
            mod.EvidenceStep(name="docker daemon availability", status="blocked", seconds=0.1, command=[]),
        ]
    )
    assert mod._exit_code(incomplete, strict_complete=False) == 0
    assert mod._exit_code(incomplete, strict_complete=True) == 2

    failed = mod.EvidenceReport()
    failed.steps.append(mod.EvidenceStep(name="release gate", status="failed", seconds=1.0, command=[]))
    assert mod._exit_code(failed, strict_complete=False) == 1
    assert mod._exit_code(failed, strict_complete=True) == 1


def test_evidence_payload_includes_handoff_artifact_paths():
    mod = _collector_module()
    report = mod.EvidenceReport(
        gap_report_path="reports/closed-beta-gap-report-test.md",
        launch_packet_path="reports/closed-beta-launch-packet-test.md",
        store_readiness_matrix_path="reports/store-readiness-matrix-test.md",
        objective_audit_path="reports/closed-beta-objective-audit-test.md",
    )
    report.steps.extend(
        [
            mod.EvidenceStep(name="gap report", status="passed", seconds=0.1, command=[]),
            mod.EvidenceStep(name="store readiness matrix", status="passed", seconds=0.1, command=[]),
            mod.EvidenceStep(name="launch packet", status="passed", seconds=0.1, command=[]),
            mod.EvidenceStep(name="objective audit", status="passed", seconds=0.1, command=[]),
        ]
    )

    payload = mod._report_payload(report)

    assert payload["gap_report_path"] == "reports/closed-beta-gap-report-test.md"
    assert payload["launch_packet_path"] == "reports/closed-beta-launch-packet-test.md"
    assert payload["store_readiness_matrix_path"] == "reports/store-readiness-matrix-test.md"
    assert payload["objective_audit_path"] == "reports/closed-beta-objective-audit-test.md"
    assert payload["passed"] is True
