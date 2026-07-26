from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _launch_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / "generate_launch_packet.py"
    spec = importlib.util.spec_from_file_location("generate_launch_packet", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_evidence(tmp_path: Path) -> Path:
    passed = [
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
    ]
    steps = [{"name": name, "status": "passed", "seconds": 0.1, "command": []} for name in passed]
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
    evidence = {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "passed": True,
        "release_evidence_complete": False,
        "steps": steps,
        "report_path": "reports/closed-beta-evidence-20260701T000000Z.json",
        "gap_report_path": "reports/closed-beta-gap-report-20260701T000000Z.md",
        "host_capabilities_path": "reports/host-capabilities-20260701T000000Z.json",
        "external_proof_path": "",
        "store_readiness_matrix_path": "reports/store-readiness-matrix-20260701T000000Z.md",
        "objective_audit_path": "reports/closed-beta-objective-audit-20260701T000000Z.md",
    }
    path = tmp_path / "closed-beta-evidence-20260701T000000Z.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def test_launch_packet_generation_separates_local_founder_from_public_beta(tmp_path: Path) -> None:
    mod = _launch_module()
    evidence_path = _synthetic_evidence(tmp_path)

    result = mod.write_launch_packet_for_evidence(evidence_path, output_dir=tmp_path)
    packet = result["packet"]
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")

    assert packet["app"] == "Thought Pins"
    assert packet["launch_decision"]["status"] == "local_founder_ready_hold_public_beta"
    tracks = {track["id"]: track for track in packet["tracks"]}
    assert tracks["local_founder_telegram"]["status"] == "passed"
    assert tracks["web_closed_beta"]["status"] == "blocked"
    assert tracks["host_capability_preflight"]["status"] == "passed"
    assert tracks["portable_external_proof"]["status"] == "needs_live_evidence"
    assert tracks["infra_rls"]["status"] == "blocked"
    assert tracks["native_store_shells"]["status"] == "passed"
    assert "Thought Pins Closed-Beta Launch Packet" in markdown
    assert "Docker Compose And PostgreSQL RLS" in markdown
    assert packet["artifact_paths"]["host_capabilities_report"].endswith("host-capabilities-20260701T000000Z.json")
    assert "external_proof_report" in packet["artifact_paths"]
    assert packet["artifact_paths"]["store_readiness_matrix"].endswith("store-readiness-matrix-20260701T000000Z.md")
    assert packet["artifact_paths"]["objective_audit"].endswith("closed-beta-objective-audit-20260701T000000Z.md")
    assert "cd frontend && npm run smoke:web" in markdown
    assert "check_external_proof_artifacts.py" in markdown
    assert "check_store_readiness_matrix.py" in markdown
    assert "generate_objective_audit.py" in markdown
    assert "closed-beta-objective-audit" in markdown
    assert ".\\scripts\\run_compose_rehearsal.ps1" in markdown


def test_launch_packet_check_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_launch_packet.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Launch packet check passed." in result.stdout
