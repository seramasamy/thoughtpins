"""Generate a closed-beta gap report from redacted evidence.

The report is deliberately boring: code gaps are failed checks, infrastructure
blockers are blocked checks, and account/product handoff tasks come from the
store submission packet. It gives a reviewer one place to see what is code vs.
external setup.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
STORE_PACKET = ROOT / "deploy" / "store" / "submission-packet.json"
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

STEP_REMEDIATION = {
    "docker daemon availability": {
        "class": "infrastructure",
        "impact": "Full Docker Compose rehearsal and live PostgreSQL RLS proof cannot run on this host.",
        "next": "Run python scripts/check_rls_static.py locally, then .\\scripts\\run_compose_rehearsal.ps1 on a machine with Docker daemon access; it runs Compose, web smoke, live API smoke, backup restore, and PostgreSQL RLS verification.",
    },
    "playwright web smoke": {
        "class": "environment",
        "impact": "Browser screenshots and axe runtime proof are unavailable in this Windows sandbox.",
        "next": "Run cd frontend && npm run smoke:web in an unrestricted shell, Linux runner, or CI with Playwright browsers installed.",
    },
    "live article provider smoke": {
        "class": "optional-live-provider",
        "impact": "Offline article/library coverage passed, but paid/live provider credentials were not exercised in this evidence run.",
        "next": "Run scripts/collect_closed_beta_evidence.py --live-article after deciding to spend provider credits.",
    },
    "runtime feature smoke": {
        "class": "runtime",
        "impact": "The main product loop was not exercised against a running API.",
        "next": "Start the API and rerun evidence with --api-base-url http://127.0.0.1:8420.",
    },
    "founder runtime smoke": {
        "class": "runtime",
        "impact": "Founder/local mode was not exercised against a running API.",
        "next": "Start the local API and rerun evidence with --api-base-url.",
    },
    "telegram API smoke": {
        "class": "external-service",
        "impact": "Telegram token/API reachability was not checked in this evidence run.",
        "next": "Rerun evidence with --telegram-api when the Telegram adapter should be validated.",
    },
    "external proof artifacts": {
        "class": "infrastructure-proof",
        "impact": "Portable Compose/RLS and Playwright proof reports were not validated in this run.",
        "next": "Run python scripts/check_external_proof_artifacts.py --compose-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke, then rerun evidence with those paths.",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Thought Pins closed-beta gap report.")
    parser.add_argument("evidence", nargs="?", help="Path to closed-beta evidence JSON. Defaults to latest report.")
    parser.add_argument("--json", action="store_true", help="Also write a JSON summary next to the Markdown report.")
    parser.add_argument(
        "--print", action="store_true", dest="print_report", help="Print the Markdown report to stdout."
    )
    args = parser.parse_args()

    evidence_path = Path(args.evidence) if args.evidence else latest_evidence_path()
    result = write_gap_report_for_evidence(evidence_path, write_json=args.json)
    if args.print_report:
        print(Path(result["markdown_path"]).read_text(encoding="utf-8"))
    else:
        print(f"Gap report written: {result['markdown_path']}")
        if result.get("json_path"):
            print(f"Gap report JSON written: {result['json_path']}")
    return 0


def latest_evidence_path() -> Path:
    reports = sorted(REPORTS.glob("closed-beta-evidence-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        raise FileNotFoundError("No closed-beta evidence report found under reports/.")
    return reports[0]


def write_gap_report_for_evidence(evidence_path: str | Path, *, write_json: bool = True) -> dict[str, Any]:
    evidence_file = Path(evidence_path)
    evidence = json.loads(evidence_file.read_text(encoding="utf-8-sig"))
    summary = build_gap_summary(evidence, evidence_file=evidence_file)
    stamp = _stamp_from_evidence(evidence, evidence_file)
    REPORTS.mkdir(parents=True, exist_ok=True)
    markdown_path = REPORTS / f"closed-beta-gap-report-{stamp}.md"
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    result: dict[str, Any] = {"markdown_path": str(markdown_path), "summary": summary}
    if write_json:
        json_path = REPORTS / f"closed-beta-gap-report-{stamp}.json"
        json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        result["json_path"] = str(json_path)
    return result


def build_gap_summary(evidence: dict[str, Any], *, evidence_file: Path | None = None) -> dict[str, Any]:
    steps = evidence.get("steps") or []
    failed = [step for step in steps if step.get("status") == "failed"]
    blocked = [step for step in steps if step.get("status") == "blocked"]
    skipped = [step for step in steps if step.get("status") == "skipped"]
    passed = [step for step in steps if step.get("status") == "passed"]
    packet = _load_store_packet()

    external_proof_passed = any(
        step.get("name") == "external proof artifacts" and step.get("status") == "passed" for step in steps
    )
    substituted_external_proof = _substituted_by_external_proof(blocked + skipped) if external_proof_passed else []
    effective_blocked = [step for step in blocked if step.get("name") not in substituted_external_proof]
    effective_skipped = [step for step in skipped if step.get("name") not in substituted_external_proof]

    code_gaps = [_step_gap(step, default_class="code") for step in failed]
    infrastructure_blockers = [_step_gap(step, default_class="infrastructure") for step in effective_blocked]
    deferred_live_checks = [_step_gap(step, default_class="deferred-live-check") for step in effective_skipped]
    external_handoff = [
        {"item": item, "class": _external_class(item)}
        for item in packet.get("known_external_blockers_before_submission", [])
    ]
    readiness = _readiness_label(code_gaps, infrastructure_blockers, deferred_live_checks)

    summary = {
        "app": evidence.get("app", "Thought Pins"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evidence": str(evidence_file) if evidence_file else evidence.get("report_path", ""),
        "evidence_generated_at_utc": evidence.get("generated_at_utc", ""),
        "readiness": readiness,
        "release_gate_passed": bool(evidence.get("passed")) and not failed,
        "release_evidence_complete": bool(evidence.get("release_evidence_complete")),
        "counts": {
            "passed": len(passed),
            "failed": len(failed),
            "blocked": len(blocked),
            "skipped": len(skipped),
        },
        "code_gaps": code_gaps,
        "infrastructure_blockers": infrastructure_blockers,
        "deferred_live_checks": deferred_live_checks,
        "external_account_and_submission_tasks": external_handoff,
        "passed_evidence": [step.get("name", "unknown") for step in passed],
        "substituted_by_external_proof": substituted_external_proof,
        "next_commands": _next_commands(infrastructure_blockers, deferred_live_checks),
    }
    return _redact_payload(summary)


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Thought Pins Closed-Beta Gap Report",
        "",
        f"Generated: {summary['generated_at_utc']}",
        f"Source evidence: `{summary.get('source_evidence') or 'unknown'}`",
        f"Readiness: **{summary['readiness']}**",
        "",
        "## Summary",
        "",
        f"- Release gate passed: `{str(summary['release_gate_passed']).lower()}`",
        f"- Evidence complete: `{str(summary['release_evidence_complete']).lower()}`",
        f"- Passed checks: `{summary['counts']['passed']}`",
        f"- Failed checks: `{summary['counts']['failed']}`",
        f"- Blocked checks: `{summary['counts']['blocked']}`",
        f"- Skipped checks: `{summary['counts']['skipped']}`",
        "",
        "## Code Gaps",
        "",
    ]
    lines.extend(_gap_lines(summary["code_gaps"], empty="No code gaps are proven by the current evidence."))
    lines.extend(["", "## Infrastructure Or Host Blockers", ""])
    lines.extend(
        _gap_lines(
            summary["infrastructure_blockers"], empty="No infrastructure blockers are present in the current evidence."
        )
    )
    lines.extend(["", "## Deferred Live Checks", ""])
    lines.extend(_gap_lines(summary["deferred_live_checks"], empty="No live checks were skipped."))
    lines.extend(["", "## External Account And Submission Tasks", ""])
    if summary["external_account_and_submission_tasks"]:
        for item in summary["external_account_and_submission_tasks"]:
            lines.append(f"- `{item['class']}`: {item['item']}")
    else:
        lines.append("No external account or store-console tasks are listed.")
    lines.extend(["", "## Substituted By External Proof", ""])
    if summary.get("substituted_by_external_proof"):
        for name in summary["substituted_by_external_proof"]:
            lines.append(f"- {name}")
    else:
        lines.append("No local host limitations were substituted by external proof artifacts.")
    lines.extend(["", "## Passed Evidence", ""])
    for name in summary["passed_evidence"]:
        lines.append(f"- {name}")
    lines.extend(["", "## Next Commands", ""])
    for command in summary["next_commands"]:
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def _gap_lines(items: list[dict[str, Any]], *, empty: str) -> list[str]:
    if not items:
        return [empty]
    lines: list[str] = []
    for item in items:
        lines.append(f"- **{item['name']}** (`{item['class']}`): {item['impact']}")
        lines.append(f"  Next: {item['next']}")
    return lines


def _substituted_by_external_proof(steps: list[dict[str, Any]]) -> list[str]:
    substitutable = {"docker daemon availability", "playwright web smoke"}
    return sorted({str(step.get("name") or "unknown") for step in steps if step.get("name") in substitutable})


def _step_gap(step: dict[str, Any], *, default_class: str) -> dict[str, Any]:
    name = str(step.get("name") or "unknown")
    known = STEP_REMEDIATION.get(name, {})
    reason = str(step.get("reason") or "")
    impact = known.get("impact") or f"Evidence step did not pass: {reason or step.get('status', 'unknown status')}."
    next_step = (
        known.get("next")
        or "Inspect the command output tail in the evidence JSON, fix the underlying issue, and rerun the release evidence collector."
    )
    return {
        "name": name,
        "class": known.get("class", default_class),
        "status": step.get("status", "unknown"),
        "reason": reason,
        "impact": impact,
        "next": next_step,
        "command": step.get("command", []),
    }


def _readiness_label(
    code_gaps: list[dict[str, Any]], blockers: list[dict[str, Any]], skipped: list[dict[str, Any]]
) -> str:
    if code_gaps:
        return "not release-ready: code gaps remain"
    if blockers:
        return "code-ready pending infrastructure proof"
    if skipped:
        return "code-ready pending requested live checks"
    return "evidence-complete closed-beta candidate"


def _next_commands(blockers: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> list[str]:
    commands = ["python scripts/release_check.py --skip-quality"]
    names = {item["name"] for item in blockers + skipped}
    if "docker daemon availability" in names:
        commands.append("python scripts/check_rls_static.py")
        commands.append(".\\scripts\\run_compose_rehearsal.ps1")
        commands.append("python scripts/verify_postgres_rls.py")
    if "playwright web smoke" in names:
        commands.append("cd frontend && npm run smoke:web")
    final_command = "python scripts/collect_closed_beta_evidence.py --api-base-url http://127.0.0.1:8420 --telegram-api --web-smoke --strict-complete"
    if "external proof artifacts" in names:
        commands.append(
            "python scripts/check_external_proof_artifacts.py --compose-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke"
        )
        final_command += " --compose-rehearsal-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke"
    if "live article provider smoke" in names:
        commands.append("python scripts/collect_closed_beta_evidence.py --live-article")
    commands.append(final_command)
    return commands


def _external_class(item: str) -> str:
    lowered = item.lower()
    if "developer" in lowered or "console" in lowered or "store" in lowered:
        return "store-account"
    if "deploy" in lowered or "staging" in lowered or "https" in lowered or "domain" in lowered:
        return "infrastructure"
    if "rotate" in lowered or "credential" in lowered or "secret" in lowered:
        return "secret-ops"
    return "submission-handoff"


def _load_store_packet() -> dict[str, Any]:
    if not STORE_PACKET.is_file():
        return {}
    return json.loads(STORE_PACKET.read_text(encoding="utf-8-sig"))


def _stamp_from_evidence(evidence: dict[str, Any], evidence_file: Path) -> str:
    match = re.search(r"(\d{8}T\d{6}Z)", evidence_file.name)
    if match:
        return match.group(1)
    generated = str(evidence.get("generated_at_utc", ""))
    digits = re.sub(r"[^0-9]", "", generated)[:14]
    if len(digits) >= 14:
        return f"{digits[:8]}T{digits[8:14]}Z"
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
