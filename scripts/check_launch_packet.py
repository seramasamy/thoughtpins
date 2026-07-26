"""Validate that the launch-packet generator produces an honest handoff."""

from __future__ import annotations

import json
import re
from pathlib import Path

from generate_launch_packet import write_launch_packet_for_evidence

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp" / "launch-packet-check"
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
]


def main() -> int:
    failures: list[str] = []
    TMP.mkdir(parents=True, exist_ok=True)
    evidence_path = TMP / "closed-beta-evidence-20260701T000000Z.json"
    evidence_path.write_text(json.dumps(_synthetic_evidence(), indent=2), encoding="utf-8")
    try:
        result = write_launch_packet_for_evidence(evidence_path, output_dir=TMP)
    except Exception as exc:  # pragma: no cover - command-line guard
        failures.append(f"launch packet generation failed: {exc}")
        return _finish(failures)

    markdown_path = Path(result["markdown_path"])
    json_path = Path(result["json_path"])
    if not markdown_path.is_file():
        failures.append("launch packet Markdown was not written")
    if not json_path.is_file():
        failures.append("launch packet JSON was not written")
        return _finish(failures)

    try:
        packet = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"launch packet JSON was unreadable: {type(exc).__name__}")
        return _finish(failures)
    markdown = markdown_path.read_text(encoding="utf-8-sig") if markdown_path.is_file() else ""
    _check_packet(packet, markdown, failures)
    _check_no_secrets(markdown + "\n" + json.dumps(packet), failures)
    return _finish(failures)


def _synthetic_evidence() -> dict:
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
    ]
    steps = [{"name": name, "status": "passed", "seconds": 0.1, "command": []} for name in passed_steps]
    steps.append(
        {
            "name": "external proof artifacts",
            "status": "skipped",
            "seconds": 0.0,
            "command": [],
            "reason": "not provided",
        }
    )
    steps.append(
        {
            "name": "docker daemon availability",
            "status": "blocked",
            "seconds": 0.1,
            "command": [],
            "reason": "docker daemon unavailable",
        }
    )
    steps.append(
        {"name": "playwright web smoke", "status": "blocked", "seconds": 0.1, "command": [], "reason": "spawn eperm"}
    )
    return {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "passed": True,
        "release_evidence_complete": False,
        "steps": steps,
        "report_path": str(evidence_path_placeholder()),
        "gap_report_path": "reports/closed-beta-gap-report-20260701T000000Z.md",
        "host_capabilities_path": "reports/host-capabilities-20260701T000000Z.json",
        "external_proof_path": "",
        "store_readiness_matrix_path": "reports/store-readiness-matrix-20260701T000000Z.md",
        "objective_audit_path": "reports/closed-beta-objective-audit-20260701T000000Z.md",
    }


def evidence_path_placeholder() -> Path:
    return TMP / "closed-beta-evidence-20260701T000000Z.json"


def _check_packet(packet: dict, markdown: str, failures: list[str]) -> None:
    if packet.get("app") != "Thought Pins":
        failures.append("launch packet app must be Thought Pins")
    decision = packet.get("launch_decision") or {}
    if decision.get("status") != "local_founder_ready_hold_public_beta":
        failures.append("launch packet must hold public beta when Docker/Playwright proof is blocked")
    tracks = {item.get("id"): item for item in packet.get("tracks") or []}
    required_tracks = {
        "local_founder_telegram",
        "web_closed_beta",
        "host_capability_preflight",
        "portable_external_proof",
        "infra_rls",
        "obsidian_second_brain",
        "native_store_shells",
    }
    missing = required_tracks - tracks.keys()
    if missing:
        failures.append(f"launch packet missing tracks: {sorted(missing)}")
    if tracks.get("local_founder_telegram", {}).get("status") != "passed":
        failures.append("local founder Telegram track should be passed in synthetic evidence")
    if tracks.get("web_closed_beta", {}).get("status") != "blocked":
        failures.append("web closed beta track should be blocked by Playwright synthetic evidence")
    if tracks.get("host_capability_preflight", {}).get("status") != "passed":
        failures.append("host capability track should pass in synthetic evidence")
    if tracks.get("portable_external_proof", {}).get("status") != "needs_live_evidence":
        failures.append("portable external proof track should need live evidence in synthetic evidence")
    if tracks.get("native_store_shells", {}).get("status") != "passed":
        failures.append("native store shell source track should pass in synthetic evidence")
    commands = packet.get("commands") or {}
    flat_commands = "\n".join(command for values in commands.values() for command in values)
    for marker in [
        "python scripts/release_check.py --skip-quality",
        "python scripts/check_rls_static.py",
        ".\\scripts\\run_compose_rehearsal.ps1",
        "python scripts/verify_postgres_rls.py",
        "cd frontend && npm run smoke:web",
        "python scripts/generate_launch_packet.py",
        "python scripts/check_host_capabilities.py",
        "python scripts/check_external_proof_artifacts.py --self-test",
        "python scripts/check_store_readiness_matrix.py --self-test",
        "python scripts/generate_store_readiness_matrix.py",
        "python scripts/generate_objective_audit.py",
    ]:
        if marker not in flat_commands:
            failures.append(f"launch packet commands missing {marker}")
    for marker in [
        "Thought Pins Closed-Beta Launch Packet",
        "Local Founder Telegram",
        "Web Closed Beta",
        "Host Capability Preflight",
        "Portable External Proof",
        "Docker Compose And PostgreSQL RLS",
        "Obsidian Second-Brain Export",
        "Native Store Shells",
    ]:
        if marker not in markdown:
            failures.append(f"launch packet markdown missing {marker}")
    artifacts = packet.get("artifact_paths") or {}
    for key in [
        "deployment_packet",
        "store_submission_packet",
        "native_review_handoff",
        "evidence",
        "gap_report",
        "host_capabilities_report",
    ]:
        if not artifacts.get(key):
            failures.append(f"launch packet artifact_paths missing {key}")
    if "external_proof_report" not in artifacts:
        failures.append("launch packet artifact_paths missing external_proof_report")
    if not artifacts.get("store_readiness_matrix"):
        failures.append("launch packet artifact_paths missing store_readiness_matrix")
    if not artifacts.get("objective_audit"):
        failures.append("launch packet artifact_paths missing objective_audit")


def _check_no_secrets(text: str, failures: list[str]) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append("launch packet contains secret-like material")
            return


def _finish(failures: list[str]) -> int:
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Launch packet check failed: {len(failures)} failure(s).")
        return 1
    print("Launch packet check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
