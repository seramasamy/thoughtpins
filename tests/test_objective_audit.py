from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load_script(name: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_objective_audit_marks_current_host_limitations_as_external_pending() -> None:
    mod = _load_script("generate_objective_audit")
    audit = mod.build_objective_audit(_evidence_with_host_blockers())

    assert audit["status"] == "code-ready pending external proof"
    assert audit["counts"]["failed_or_missing"] == 0
    requirements = {item["id"]: item for item in audit["requirements"]}
    assert requirements["production_rehearsal"]["status"] == "pending_external_proof"
    assert requirements["web_mobile_review_ux"]["status"] == "pending_external_proof"
    assert requirements["app_store_compliance"]["status"] == "passed"
    assert requirements["second_brain_quality"]["status"] == "passed"
    assert "cd frontend && npm run smoke:web" in audit["next_commands"]


def test_objective_audit_accepts_complete_external_proof_substitution() -> None:
    mod = _load_script("generate_objective_audit")
    evidence = _evidence_with_host_blockers()
    for step in evidence["steps"]:
        if step["name"] in {"external proof artifacts", "docker daemon availability", "playwright web smoke"}:
            step["status"] = "passed"
            step["reason"] = ""
    evidence["release_evidence_complete"] = True

    audit = mod.build_objective_audit(evidence)

    assert audit["status"] == "closed-beta objective complete"
    assert audit["counts"] == {"passed": 6, "pending_external_proof": 0, "failed_or_missing": 0}


def test_objective_audit_flags_missing_required_evidence() -> None:
    mod = _load_script("generate_objective_audit")
    evidence = _evidence_with_host_blockers()
    evidence["steps"] = [step for step in evidence["steps"] if step["name"] != "runtime feature smoke"]

    audit = mod.build_objective_audit(evidence)

    assert audit["status"] == "not closed-beta ready: code or evidence gaps remain"
    runtime_items = [
        item
        for requirement in audit["requirements"]
        for item in requirement["evidence"]
        if item["name"] == "runtime feature smoke"
    ]
    assert runtime_items
    assert all(item["status"] == "missing" for item in runtime_items)


def test_objective_audit_command_writes_reports(tmp_path: Path) -> None:
    evidence_path = tmp_path / "closed-beta-evidence-20260701T000000Z.json"
    evidence_path.write_text(json.dumps(_evidence_with_host_blockers()), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/generate_objective_audit.py", str(evidence_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Objective audit written:" in result.stdout
    assert (ROOT / "reports" / "closed-beta-objective-audit-20260701T000000Z.md").is_file()
    assert (ROOT / "reports" / "closed-beta-objective-audit-20260701T000000Z.json").is_file()


def _evidence_with_host_blockers() -> dict:
    passed_steps = [
        "quick release gate",
        "review account packet",
        "app store compliance",
        "store submission packet",
        "review notes packet",
        "closed-beta deployment packet",
        "native review handoff",
        "public export hygiene",
        "backup restore smoke",
        "obsidian vault stress",
        "production parity",
        "startup shutdown smoke",
        "runtime feature smoke",
        "founder runtime smoke",
        "telegram API smoke",
        "host capability preflight",
        "live article provider smoke",
        "gap report",
        "store readiness matrix",
        "launch packet",
        "web review harness",
        "web app product contract",
        "mobile core scaffold",
    ]
    steps = [{"name": name, "status": "passed", "seconds": 0.1, "command": []} for name in passed_steps]
    steps.extend(
        [
            {
                "name": "external proof artifacts",
                "status": "skipped",
                "seconds": 0.0,
                "command": [],
                "reason": "not provided",
            },
            {
                "name": "docker daemon availability",
                "status": "blocked",
                "seconds": 0.1,
                "command": [],
                "reason": "docker daemon unavailable",
            },
            {
                "name": "playwright web smoke",
                "status": "blocked",
                "seconds": 0.1,
                "command": [],
                "reason": "spawn eperm",
            },
        ]
    )
    return {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "passed": True,
        "release_evidence_complete": False,
        "steps": steps,
        "report_path": "reports/closed-beta-evidence-20260701T000000Z.json",
    }
