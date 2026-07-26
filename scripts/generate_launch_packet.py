"""Generate a closed-beta launch packet from current evidence.

This sits above the deployment/store/gap packets. It answers the practical
question before a beta push: what is ready, what is blocked by the host or
accounts, and what exact commands prove the remaining gates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from generate_gap_report import build_gap_summary, latest_evidence_path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DEPLOYMENT_PACKET = ROOT / "deploy" / "closed-beta-deployment-packet.json"
STORE_PACKET = ROOT / "deploy" / "store" / "submission-packet.json"
NATIVE_HANDOFF = ROOT / "deploy" / "store" / "native-review-handoff.json"

SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
    re.compile(r"(?i)((?:api[_-]?key|auth[_-]?token|bot[_-]?token|password|jwt[_-]?secret)\s*[=:]\s*)[^\s,;'\"]+"),
    re.compile(r"(postgresql(?:\+psycopg2)?://)([^:@/]+):([^@/]+)@"),
    re.compile(r"(redis://)(:[^@/]+@)"),
]

TRACKS = [
    {
        "id": "local_founder_telegram",
        "name": "Local Founder Telegram",
        "required_steps": ["runtime feature smoke", "founder runtime smoke", "telegram API smoke"],
        "ready_when": "All three runtime checks pass against a disposable or local API.",
        "next_if_not_ready": "Run python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke and inspect the failed or skipped step.",
    },
    {
        "id": "web_closed_beta",
        "name": "Web Closed Beta",
        "required_steps": [
            "quick release gate",
            "app store compliance",
            "closed-beta deployment packet",
            "runtime feature smoke",
            "playwright web smoke",
        ],
        "ready_when": "Release, runtime, deployment packet, and Playwright screenshot/a11y smoke all pass.",
        "next_if_not_ready": "Run cd frontend && npm run smoke:web in an unrestricted shell or CI with Playwright browsers installed.",
    },
    {
        "id": "host_capability_preflight",
        "name": "Host Capability Preflight",
        "required_steps": ["host capability preflight"],
        "ready_when": "The host capability report is generated without command or redaction errors.",
        "next_if_not_ready": "Run python scripts/check_host_capabilities.py --json and fix the reported host tooling issue.",
    },
    {
        "id": "portable_external_proof",
        "name": "Portable External Proof",
        "required_steps": ["external proof artifacts"],
        "ready_when": "Compose/RLS and Playwright JSON reports plus screenshots validate from reports/.",
        "next_if_not_ready": "Run python scripts/check_external_proof_artifacts.py --compose-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke, then rerun evidence with those paths.",
    },
    {
        "id": "infra_rls",
        "name": "Docker Compose And PostgreSQL RLS",
        "required_steps": ["production parity", "startup shutdown smoke", "docker daemon availability"],
        "ready_when": "Compose rehearsal and non-owner PostgreSQL RLS verification pass on a Docker-enabled host.",
        "next_if_not_ready": "Run python scripts/check_rls_static.py locally, then .\\scripts\\run_compose_rehearsal.ps1 and python scripts/verify_postgres_rls.py with migration/app-role URLs on a PostgreSQL host.",
    },
    {
        "id": "obsidian_second_brain",
        "name": "Obsidian Second-Brain Export",
        "required_steps": ["obsidian vault stress", "backup restore smoke", "runtime feature smoke"],
        "ready_when": "Vault stress, backup/restore, and runtime memory flows pass.",
        "next_if_not_ready": "Run python scripts/stress_vault_obsidian.py --offline-fixture --obsidian-defaults --json and fix any export/link validation errors.",
    },
    {
        "id": "native_store_shells",
        "name": "Native Store Shells",
        "required_steps": ["quick release gate", "native review handoff", "store submission packet"],
        "ready_when": "Source-level iOS/Android review shells and core contracts pass; actual submission still requires device builds.",
        "next_if_not_ready": "Run python scripts/check_native_review_handoff.py and python scripts/check_mobile_core.py, then compile in Xcode/Android Studio.",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Thought Pins closed-beta launch packet.")
    parser.add_argument("evidence", nargs="?", help="Path to closed-beta evidence JSON. Defaults to latest report.")
    parser.add_argument("--output-dir", default=str(REPORTS), help="Directory for launch packet Markdown/JSON.")
    parser.add_argument("--print", action="store_true", dest="print_packet", help="Print the Markdown packet.")
    args = parser.parse_args()

    evidence_path = Path(args.evidence) if args.evidence else latest_evidence_path()
    result = write_launch_packet_for_evidence(evidence_path, output_dir=Path(args.output_dir))
    if args.print_packet:
        print(Path(result["markdown_path"]).read_text(encoding="utf-8"))
    else:
        print(f"Launch packet written: {result['markdown_path']}")
        print(f"Launch packet JSON written: {result['json_path']}")
    return 0


def write_launch_packet_for_evidence(evidence_path: str | Path, *, output_dir: Path = REPORTS) -> dict[str, Any]:
    evidence_file = Path(evidence_path)
    evidence = _load_json(evidence_file)
    gap_summary = build_gap_summary(evidence, evidence_file=evidence_file)
    packet = build_launch_packet(evidence, gap_summary, evidence_file=evidence_file)
    stamp = _stamp_from_evidence(evidence, evidence_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"closed-beta-launch-packet-{stamp}.md"
    json_path = output_dir / f"closed-beta-launch-packet-{stamp}.json"
    _atomic_write_text(markdown_path, render_markdown(packet))
    _atomic_write_text(json_path, json.dumps(packet, indent=2, sort_keys=True))
    return {"markdown_path": str(markdown_path), "json_path": str(json_path), "packet": packet}


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_launch_packet(
    evidence: dict[str, Any], gap_summary: dict[str, Any], *, evidence_file: Path | None = None
) -> dict[str, Any]:
    deployment = _load_json(DEPLOYMENT_PACKET)
    store = _load_json(STORE_PACKET)
    native = _load_json(NATIVE_HANDOFF)
    steps_by_name = {str(step.get("name")): step for step in evidence.get("steps") or []}
    tracks = [_track_summary(track, steps_by_name) for track in TRACKS]
    failed = gap_summary.get("code_gaps", [])
    blockers = gap_summary.get("infrastructure_blockers", [])
    skipped = gap_summary.get("deferred_live_checks", [])
    native_status = native.get("status") or {}

    packet = {
        "app": evidence.get("app", "Thought Pins"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evidence": str(evidence_file) if evidence_file else evidence.get("report_path", ""),
        "source_gap_report": evidence.get("gap_report_path", ""),
        "readiness": gap_summary.get("readiness", "unknown"),
        "launch_decision": _launch_decision(failed, blockers, skipped, tracks),
        "summary": {
            "release_gate_passed": bool(gap_summary.get("release_gate_passed")),
            "evidence_complete": bool(gap_summary.get("release_evidence_complete")),
            "passed_checks": gap_summary.get("counts", {}).get("passed", 0),
            "failed_checks": gap_summary.get("counts", {}).get("failed", 0),
            "blocked_checks": gap_summary.get("counts", {}).get("blocked", 0),
            "skipped_checks": gap_summary.get("counts", {}).get("skipped", 0),
        },
        "tracks": tracks,
        "required_external_proof": {
            "code_gaps": failed,
            "host_or_infrastructure_blockers": blockers,
            "deferred_live_checks": skipped,
            "store_account_and_submission_tasks": gap_summary.get("external_account_and_submission_tasks", []),
        },
        "commands": _commands(deployment, store),
        "artifact_paths": {
            "deployment_packet": str(DEPLOYMENT_PACKET.relative_to(ROOT)),
            "store_submission_packet": str(STORE_PACKET.relative_to(ROOT)),
            "native_review_handoff": str(NATIVE_HANDOFF.relative_to(ROOT)),
            "evidence": str(evidence_file) if evidence_file else evidence.get("report_path", ""),
            "gap_report": evidence.get("gap_report_path", ""),
            "host_capabilities_report": evidence.get("host_capabilities_path", ""),
            "external_proof_report": evidence.get("external_proof_path", ""),
            "store_readiness_matrix": evidence.get("store_readiness_matrix_path", ""),
            "objective_audit": evidence.get("objective_audit_path", ""),
        },
        "native_store_submission": {
            "source_shells_ready": native_status.get("native_ui_shells_ready") is True,
            "native_store_submission_ready": native_status.get("native_store_submission_ready") is True,
            "reason": native_status.get("native_store_submission_reason", ""),
            "remaining_blockers": native.get("native_submission_blockers", []),
        },
        "public_policy_urls": deployment.get("public_hosts", {}),
        "official_store_references": store.get("official_references", {}),
        "secret_hygiene": deployment.get("secret_handling", {}),
    }
    return _redact_payload(packet)


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Thought Pins Closed-Beta Launch Packet",
        "",
        f"Generated: {packet['generated_at_utc']}",
        f"Source evidence: `{packet.get('source_evidence') or 'unknown'}`",
        f"Readiness: **{packet['readiness']}**",
        f"Decision: **{packet['launch_decision']['status']}**",
        "",
        "## Decision",
        "",
        packet["launch_decision"]["reason"],
        "",
        "## Evidence Summary",
        "",
    ]
    for key, value in packet["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Product Tracks", ""])
    for track in packet["tracks"]:
        lines.append(f"- **{track['name']}**: `{track['status']}`")
        lines.append(f"  Ready when: {track['ready_when']}")
        if track["missing_or_blocked"]:
            lines.append(f"  Next: {track['next_if_not_ready']}")
            for item in track["missing_or_blocked"]:
                lines.append(f"  - {item['name']}: `{item['status']}` {item.get('reason') or ''}".rstrip())
    lines.extend(["", "## Required External Proof", ""])
    _append_gap_list(lines, "Code gaps", packet["required_external_proof"]["code_gaps"])
    _append_gap_list(
        lines, "Host or infrastructure blockers", packet["required_external_proof"]["host_or_infrastructure_blockers"]
    )
    _append_gap_list(lines, "Deferred live checks", packet["required_external_proof"]["deferred_live_checks"])
    lines.extend(["", "## Store And Native Handoff", ""])
    native = packet["native_store_submission"]
    lines.append(f"- Native source shells ready: `{native['source_shells_ready']}`")
    lines.append(f"- Native store submission ready: `{native['native_store_submission_ready']}`")
    if native.get("reason"):
        lines.append(f"- Reason: {native['reason']}")
    for blocker in native.get("remaining_blockers", []):
        lines.append(f"- Native blocker: {blocker}")
    lines.extend(["", "## Commands", ""])
    for group, commands in packet["commands"].items():
        lines.append(f"### {group.replace('_', ' ').title()}")
        for command in commands:
            lines.append(f"- `{command}`")
        lines.append("")
    lines.extend(["## Artifacts", ""])
    for key, value in packet["artifact_paths"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def _track_summary(track: dict[str, Any], steps_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing_or_blocked: list[dict[str, str]] = []
    observed: list[dict[str, str]] = []
    for name in track["required_steps"]:
        step = steps_by_name.get(name)
        if not step and name == "quick release gate":
            step = steps_by_name.get("release gate")
        if not step:
            missing_or_blocked.append({"name": name, "status": "missing", "reason": "not present in evidence"})
            continue
        status = str(step.get("status") or "unknown")
        item = {"name": name, "status": status, "reason": str(step.get("reason") or "")}
        observed.append(item)
        if status != "passed":
            missing_or_blocked.append(item)
    if any(item["status"] == "failed" for item in observed + missing_or_blocked):
        status = "failed"
    elif any(item["status"] == "blocked" for item in observed + missing_or_blocked):
        status = "blocked"
    elif any(item["status"] in {"skipped", "missing"} for item in missing_or_blocked):
        status = "needs_live_evidence"
    else:
        status = "passed"
    return {
        "id": track["id"],
        "name": track["name"],
        "status": status,
        "required_steps": track["required_steps"],
        "observed_steps": observed,
        "missing_or_blocked": missing_or_blocked,
        "ready_when": track["ready_when"],
        "next_if_not_ready": track["next_if_not_ready"],
    }


def _launch_decision(
    failed: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    tracks: list[dict[str, Any]],
) -> dict[str, str]:
    if failed:
        return {
            "status": "hold_code_gaps",
            "reason": "Do not launch: at least one code or contract check failed. Fix failed evidence steps and rerun release/evidence gates.",
        }
    founder_track = next((track for track in tracks if track["id"] == "local_founder_telegram"), {})
    if blockers:
        local = (
            "Founder/local Telegram use is permitted by the current evidence."
            if founder_track.get("status") == "passed"
            else "Founder/local Telegram still needs runtime proof."
        )
        return {
            "status": "local_founder_ready_hold_public_beta",
            "reason": f"{local} Public closed beta is on hold until infrastructure/browser proof completes.",
        }
    if skipped:
        return {
            "status": "hold_requested_live_checks",
            "reason": "Code gates passed, but requested live checks were skipped. Run the listed commands before inviting testers.",
        }
    return {
        "status": "closed_beta_candidate",
        "reason": "All code, runtime, infrastructure, browser, and live checks in the evidence packet passed. Proceed with account/store-console handoff tasks.",
    }


def _commands(deployment: dict[str, Any], store: dict[str, Any]) -> dict[str, list[str]]:
    deployment_commands = list(deployment.get("verification_commands") or [])
    store_commands = list(store.get("evidence_commands") or [])
    return {
        "local_acceptance": [
            "python scripts/release_check.py --skip-quality",
            "python scripts/check_rls_static.py",
            "python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke",
            "python scripts/generate_launch_packet.py",
        ],
        "infrastructure_proof": [
            ".\\scripts\\run_compose_rehearsal.ps1",
            "DATABASE_URL=<migration-role-url> RLS_VERIFY_DATABASE_URL=<app-role-url> python scripts/verify_postgres_rls.py",
            "cd frontend && npm run smoke:web",
            "python scripts/check_external_proof_artifacts.py --compose-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke",
        ],
        "staging_or_review": [
            ".\\scripts\\run_staging_smoke.ps1",
            "python scripts/collect_closed_beta_evidence.py --api-base-url https://api-staging.thoughtpins.com --telegram-api --web-smoke",
            "python scripts/collect_closed_beta_evidence.py --api-base-url https://api-staging.thoughtpins.com --telegram-api --web-smoke --compose-rehearsal-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke",
            "python scripts/seed_review_account.py --export-vault --zip-vault",
        ],
        "packet_validators": _dedupe(
            [
                "python scripts/check_launch_packet.py",
                "python scripts/check_external_proof_artifacts.py --self-test",
                "python scripts/check_store_readiness_matrix.py --self-test",
                "python scripts/generate_store_readiness_matrix.py",
                "python scripts/generate_objective_audit.py",
                "python scripts/check_deployment_packet.py",
                "python scripts/check_store_submission_packet.py",
                "python scripts/check_native_review_handoff.py",
                *deployment_commands,
                *store_commands,
            ]
        ),
    }


def _append_gap_list(lines: list[str], title: str, items: list[dict[str, Any]]) -> None:
    lines.append(f"### {title}")
    if not items:
        lines.append("- None proven by current evidence.")
        return
    for item in items:
        lines.append(
            f"- **{item.get('name', item.get('class', 'item'))}**: {item.get('impact') or item.get('item') or item.get('reason') or 'See evidence.'}"
        )
        if item.get("next"):
            lines.append(f"  Next: {item['next']}")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _stamp_from_evidence(evidence: dict[str, Any], evidence_file: Path) -> str:
    match = re.search(r"(\d{8}T\d{6}Z)", evidence_file.name)
    if match:
        return match.group(1)
    generated = str(evidence.get("generated_at_utc", ""))
    digits = re.sub(r"[^0-9]", "", generated)[:14]
    if len(digits) >= 14:
        return f"{digits[:8]}T{digits[8:14]}Z"
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    return value


def _redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(postgresql"):
            redacted = pattern.sub(r"\1***:***@", redacted)
        elif pattern.pattern.startswith("(redis"):
            redacted = pattern.sub(r"\1:***@", redacted)
        elif "Bearer" in pattern.pattern:
            redacted = pattern.sub(r"\1<redacted>", redacted)
        elif "api" in pattern.pattern.lower() or "password" in pattern.pattern.lower():
            redacted = pattern.sub(r"\1<redacted>", redacted)
        else:
            redacted = pattern.sub("<redacted>", redacted)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
