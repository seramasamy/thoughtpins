"""Generate a requirement-level audit for the Thought Pins closed-beta goal.

The normal gap report answers "what failed or is blocked?". This audit answers a
slightly different question: which part of the actual closed-beta objective is
proved by current evidence, which part is still waiting on external host/account
proof, and whether any missing item is a real code gap.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_gap_report import latest_evidence_path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
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

SUBSTITUTIONS = {
    "docker daemon availability": "external proof artifacts",
    "playwright web smoke": "external proof artifacts",
}


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    evidence_steps: tuple[str, ...]
    external_steps: tuple[str, ...] = ()


REQUIREMENTS = [
    Requirement(
        id="production_rehearsal",
        title="Docker production rehearsal, migrations, RLS, backup/restore, and clean startup/shutdown",
        evidence_steps=(
            "production parity",
            "backup restore smoke",
            "startup shutdown smoke",
            "docker daemon availability",
            "external proof artifacts",
        ),
        external_steps=("docker daemon availability", "external proof artifacts"),
    ),
    Requirement(
        id="web_mobile_review_ux",
        title="Web/mobile review-ready UX, screenshots, maintenance/offline, auth, chat, ingestion, export/delete, and accessibility",
        evidence_steps=(
            "quick release gate",
            "web review harness",
            "web app product contract",
            "mobile core scaffold",
            "native review handoff",
            "playwright web smoke",
        ),
        external_steps=("playwright web smoke",),
    ),
    Requirement(
        id="app_store_compliance",
        title="Apple/Google compliance packets, account deletion, review access, policy URLs, and native handoff",
        evidence_steps=(
            "review account packet",
            "app store compliance",
            "store submission packet",
            "review notes packet",
            "closed-beta deployment packet",
            "native review handoff",
            "store readiness matrix",
        ),
    ),
    Requirement(
        id="second_brain_quality",
        title="Second-brain quality: journals, notes, recipes, documents, articles, obscure recall, Obsidian export, and provenance",
        evidence_steps=(
            "quick release gate",
            "obsidian vault stress",
            "backup restore smoke",
            "runtime feature smoke",
            "live article provider smoke",
        ),
    ),
    Requirement(
        id="production_operations",
        title="Production operations: structured/log privacy, request/runtime smoke, rate/audit health, queue recovery, export/delete, secrets, and repeatable smoke scripts",
        evidence_steps=(
            "quick release gate",
            "production parity",
            "startup shutdown smoke",
            "runtime feature smoke",
            "backup restore smoke",
            "host capability preflight",
        ),
    ),
    Requirement(
        id="full_evidence_packet",
        title="Full evidence packet with release gate, runtime, Telegram, web screenshots, mobile, Obsidian, RLS, gap and launch reports",
        evidence_steps=(
            "quick release gate",
            "runtime feature smoke",
            "founder runtime smoke",
            "telegram API smoke",
            "playwright web smoke",
            "obsidian vault stress",
            "production parity",
            "docker daemon availability",
            "external proof artifacts",
            "gap report",
            "store readiness matrix",
            "launch packet",
        ),
        external_steps=("docker daemon availability", "playwright web smoke", "external proof artifacts"),
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Thought Pins closed-beta objective audit.")
    parser.add_argument("evidence", nargs="?", help="Path to closed-beta evidence JSON. Defaults to latest report.")
    parser.add_argument("--json", action="store_true", help="Print the audit JSON.")
    parser.add_argument("--print", action="store_true", dest="print_report", help="Print the audit Markdown.")
    parser.add_argument(
        "--strict-complete",
        action="store_true",
        help="Exit nonzero unless all objective requirements are fully proven.",
    )
    args = parser.parse_args()

    evidence_path = Path(args.evidence) if args.evidence else latest_evidence_path()
    result = write_objective_audit_for_evidence(evidence_path)
    audit = result["audit"]
    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True))
    elif args.print_report:
        print(Path(result["markdown_path"]).read_text(encoding="utf-8"))
    else:
        print(f"Objective audit written: {result['markdown_path']}")
        print(f"Objective audit JSON written: {result['json_path']}")
        print(f"Objective status: {audit['status']}")
    if args.strict_complete and audit["status"] != "closed-beta objective complete":
        print("Strict objective completeness failed: unresolved requirement evidence remains.")
        return 2
    return 0 if audit["status"] != "not closed-beta ready: code or evidence gaps remain" else 1


def write_objective_audit_for_evidence(evidence_path: str | Path, *, output_dir: Path = REPORTS) -> dict[str, Any]:
    evidence_file = Path(evidence_path)
    evidence = json.loads(evidence_file.read_text(encoding="utf-8-sig"))
    audit = build_objective_audit(evidence, evidence_file=evidence_file)
    stamp = _stamp_from_evidence(evidence, evidence_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"closed-beta-objective-audit-{stamp}.md"
    json_path = output_dir / f"closed-beta-objective-audit-{stamp}.json"
    markdown_path.write_text(render_markdown(audit), encoding="utf-8")
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
    return {"markdown_path": str(markdown_path), "json_path": str(json_path), "audit": audit}


def build_objective_audit(evidence: dict[str, Any], *, evidence_file: Path | None = None) -> dict[str, Any]:
    steps_by_name = {str(step.get("name")): step for step in evidence.get("steps") or []}
    requirement_results = [_requirement_result(requirement, steps_by_name) for requirement in REQUIREMENTS]
    code_or_evidence_gaps = [
        result for result in requirement_results if result["status"] in {"failed", "missing_evidence"}
    ]
    pending_external = [result for result in requirement_results if result["status"] == "pending_external_proof"]
    if code_or_evidence_gaps:
        status = "not closed-beta ready: code or evidence gaps remain"
    elif pending_external:
        status = "code-ready pending external proof"
    else:
        status = "closed-beta objective complete"
    audit = {
        "app": evidence.get("app", "Thought Pins"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evidence": str(evidence_file) if evidence_file else evidence.get("report_path", ""),
        "evidence_generated_at_utc": evidence.get("generated_at_utc", ""),
        "status": status,
        "release_evidence_complete": bool(evidence.get("release_evidence_complete")),
        "requirements": requirement_results,
        "counts": {
            "passed": sum(1 for result in requirement_results if result["status"] == "passed"),
            "pending_external_proof": len(pending_external),
            "failed_or_missing": len(code_or_evidence_gaps),
        },
        "next_commands": _next_commands(requirement_results),
    }
    return _redact_payload(audit)


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Thought Pins Closed-Beta Objective Audit",
        "",
        f"Generated: {audit['generated_at_utc']}",
        f"Source evidence: `{audit.get('source_evidence') or 'unknown'}`",
        f"Status: **{audit['status']}**",
        "",
        "## Requirement Coverage",
        "",
    ]
    for requirement in audit["requirements"]:
        lines.append(f"- **{requirement['title']}**: `{requirement['status']}`")
        for item in requirement["evidence"]:
            reason = f" - {item['reason']}" if item.get("reason") else ""
            substitution = f" via `{item['substituted_by']}`" if item.get("substituted_by") else ""
            lines.append(f"  - {item['name']}: `{item['status']}`{substitution}{reason}")
    lines.extend(["", "## Next Commands", ""])
    for command in audit["next_commands"]:
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def _requirement_result(requirement: Requirement, steps_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_items = [_step_evidence(name, steps_by_name) for name in requirement.evidence_steps]
    unresolved = [item for item in evidence_items if item["status"] != "passed"]
    if not unresolved:
        status = "passed"
    elif any(item["status"] in {"failed", "missing"} for item in unresolved):
        status = "failed" if any(item["status"] == "failed" for item in unresolved) else "missing_evidence"
    elif all(item["name"] in requirement.external_steps or item.get("substituted_by") for item in unresolved):
        status = "pending_external_proof"
    else:
        status = "missing_evidence"
    return {
        "id": requirement.id,
        "title": requirement.title,
        "status": status,
        "evidence": evidence_items,
    }


def _step_evidence(name: str, steps_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    step = steps_by_name.get(name)
    if not step and name == "quick release gate":
        step = steps_by_name.get("release gate")
    if not step:
        return {"name": name, "status": "missing", "reason": "not present in evidence"}
    status = str(step.get("status") or "unknown")
    substituted_by = ""
    substitute_name = SUBSTITUTIONS.get(name)
    substitute = steps_by_name.get(substitute_name or "")
    if status in {"blocked", "skipped"} and substitute and substitute.get("status") == "passed":
        status = "passed"
        substituted_by = str(substitute_name)
    return {
        "name": name,
        "status": status,
        "reason": str(step.get("reason") or ""),
        "substituted_by": substituted_by,
    }


def _next_commands(requirements: list[dict[str, Any]]) -> list[str]:
    unresolved_names = {
        item["name"] for requirement in requirements for item in requirement["evidence"] if item["status"] != "passed"
    }
    commands = ["python scripts/release_check.py"]
    if {"docker daemon availability", "external proof artifacts"} & unresolved_names:
        commands.append("python scripts/check_rls_static.py")
        commands.append(".\\scripts\\run_compose_rehearsal.ps1")
        commands.append("python scripts/verify_postgres_rls.py")
    if "playwright web smoke" in unresolved_names:
        commands.append("cd frontend && npm run smoke:web")
    if "external proof artifacts" in unresolved_names:
        commands.append(
            "python scripts/check_external_proof_artifacts.py --compose-report reports/compose-rehearsal-<stamp>.json --playwright-report reports/playwright-web-smoke.json --web-smoke-dir reports/web-smoke"
        )
    commands.append(
        "python scripts/collect_closed_beta_evidence.py --api-base-url http://127.0.0.1:8420 --telegram-api --web-smoke --strict-complete"
    )
    return commands


def _stamp_from_evidence(evidence: dict[str, Any], evidence_file: Path) -> str:
    match = re.search(r"(\d{8}T\d{6}Z)", evidence_file.name)
    if match:
        return match.group(1)
    try:
        stamp = datetime.fromisoformat(str(evidence.get("generated_at_utc", "")).replace("Z", "+00:00"))
    except ValueError:
        stamp = datetime.now(timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
            redacted = pattern.sub(r"\1***@", redacted)
        elif "Bearer" in pattern.pattern:
            redacted = pattern.sub(r"\1<redacted>", redacted)
        elif (
            "api" in pattern.pattern.lower()
            or "token" in pattern.pattern.lower()
            or "password" in pattern.pattern.lower()
        ):
            redacted = pattern.sub(r"\1<redacted>", redacted)
        else:
            redacted = pattern.sub("<redacted>", redacted)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
