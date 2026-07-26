"""Generate an auditable Apple/Google store-readiness matrix.

The store packet explains what we intend to submit. This matrix ties that intent
to current local evidence so closed-beta handoff does not depend on memory or a
spreadsheet outside the repo.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
STORE_PACKET = ROOT / "deploy" / "store" / "submission-packet.json"
POLICY_REQUIREMENTS = ROOT / "deploy" / "store" / "store-policy-requirements.json"
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

REQUIREMENT_STEP_MAP = {
    "apple_review_access": ["review account packet", "review notes packet", "store submission packet"],
    "apple_live_backend": ["production parity", "startup shutdown smoke", "runtime feature smoke"],
    "apple_privacy_policy_and_retention": ["app store compliance", "store submission packet", "public export hygiene"],
    "apple_in_app_account_deletion": ["quick release gate", "runtime feature smoke"],
    "apple_sign_in_with_apple_parity": ["app store compliance", "store submission packet"],
    "apple_user_generated_content_safety_controls": [
        "app store compliance",
        "store submission packet",
        "public export hygiene",
    ],
    "apple_ai_disclosure_and_safety_reporting": [
        "app store compliance",
        "store submission packet",
        "domain readiness",
        "public export hygiene",
    ],
    "google_privacy_policy": ["app store compliance", "store submission packet", "public export hygiene"],
    "google_data_safety": ["app store compliance", "store submission packet"],
    "google_in_app_account_deletion": ["quick release gate", "runtime feature smoke"],
    "google_web_account_deletion": ["quick release gate", "app store compliance", "store submission packet"],
    "google_secure_handling_and_no_sale": ["app store compliance", "public export hygiene"],
    "google_ai_generated_content_safety": [
        "app store compliance",
        "store submission packet",
        "domain readiness",
        "public export hygiene",
    ],
    "public_build_no_founder_leakage": ["public export hygiene", "quick release gate"],
}

POLICY_SOURCE_MAX_AGE_DAYS = 120

EXTERNAL_STATUS_MARKERS = (
    "needs_public_deploy",
    "needs_store_console",
    "needs_play_console",
    "needs_client_ids",
    "needs_private_credentials",
    "needs_final_policy_review",
    "infrastructure_required",
)


class MatrixError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Thought Pins store-readiness matrix.")
    parser.add_argument(
        "evidence", nargs="?", help="Closed-beta evidence JSON. Defaults to latest report when present."
    )
    parser.add_argument("--output-dir", default=str(REPORTS), help="Directory for matrix Markdown/JSON.")
    parser.add_argument("--print", action="store_true", dest="print_matrix", help="Print Markdown matrix.")
    args = parser.parse_args()

    evidence_path = Path(args.evidence) if args.evidence else latest_evidence_path(required=False)
    result = write_store_readiness_matrix(evidence_path, output_dir=Path(args.output_dir))
    if args.print_matrix:
        print(Path(result["markdown_path"]).read_text(encoding="utf-8"))
    else:
        print(f"Store readiness matrix written: {result['markdown_path']}")
        print(f"Store readiness matrix JSON written: {result['json_path']}")
    return 0


def latest_evidence_path(*, required: bool = True) -> Path | None:
    reports = sorted(REPORTS.glob("closed-beta-evidence-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if reports:
        return reports[0]
    if required:
        raise FileNotFoundError("No closed-beta evidence report found under reports/.")
    return None


def write_store_readiness_matrix(evidence_path: str | Path | None, *, output_dir: Path = REPORTS) -> dict[str, Any]:
    evidence_file = Path(evidence_path) if evidence_path else None
    evidence = _load_json(evidence_file) if evidence_file else {}
    packet = _load_json(STORE_PACKET)
    policy = _load_json(POLICY_REQUIREMENTS)
    native = _load_json(NATIVE_HANDOFF)
    matrix = build_store_readiness_matrix(evidence, packet, policy, native, evidence_file=evidence_file)
    stamp = _stamp_from_evidence(evidence, evidence_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"store-readiness-matrix-{stamp}.md"
    json_path = output_dir / f"store-readiness-matrix-{stamp}.json"
    markdown_path.write_text(render_markdown(matrix), encoding="utf-8")
    json_path.write_text(json.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")
    return {"markdown_path": str(markdown_path), "json_path": str(json_path), "matrix": matrix}


def build_store_readiness_matrix(
    evidence: dict[str, Any],
    packet: dict[str, Any],
    policy: dict[str, Any],
    native: dict[str, Any],
    *,
    evidence_file: Path | None = None,
) -> dict[str, Any]:
    if packet.get("app_name") != "Thought Pins":
        raise MatrixError("submission packet must be for Thought Pins")
    if policy.get("app_name") != "Thought Pins":
        raise MatrixError("policy requirement packet must be for Thought Pins")

    steps = {str(step.get("name")): step for step in evidence.get("steps") or []}
    apple_gates = {item.get("name"): item for item in packet.get("apple_review_gates") or []}
    google_gates = {item.get("name"): item for item in packet.get("google_play_gates") or []}
    native_flows = native.get("required_review_flows") or []
    native_by_policy = _native_flow_index(native_flows)
    requirements = []

    for requirement in policy.get("requirements") or []:
        req_id = str(requirement.get("id") or "")
        gate = _gate_for(requirement, apple_gates, google_gates)
        evidence_refs = _dedupe([*(requirement.get("evidence") or []), *(gate.get("evidence") or [])])
        repo_refs = [_evidence_ref_status(ref) for ref in evidence_refs]
        step_refs = _step_statuses(req_id, steps)
        native_refs = native_by_policy.get(req_id, [])
        implementation_status = str(requirement.get("implementation_status") or gate.get("status") or "unknown")
        requirement_status = _requirement_status(implementation_status, repo_refs, step_refs, bool(evidence))
        requirements.append(
            {
                "id": req_id,
                "platform": requirement.get("platform"),
                "official_reference": requirement.get("official_reference"),
                "official_reference_url": (policy.get("official_references") or {}).get(
                    requirement.get("official_reference"), ""
                ),
                "policy_summary": requirement.get("policy_summary", ""),
                "local_gate": requirement.get("local_gate"),
                "implementation_status": implementation_status,
                "store_gate_status": gate.get("status", "missing"),
                "readiness": requirement_status,
                "evidence_refs": repo_refs,
                "evidence_steps": step_refs,
                "native_review_flows": native_refs,
            }
        )

    counts = _count_readiness(requirements)
    matrix = {
        "app": "Thought Pins",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evidence": str(evidence_file) if evidence_file else "",
        "evidence_generated_at_utc": evidence.get("generated_at_utc", ""),
        "source_packets": {
            "submission_packet": str(STORE_PACKET.relative_to(ROOT)),
            "policy_requirements": str(POLICY_REQUIREMENTS.relative_to(ROOT)),
            "native_review_handoff": str(NATIVE_HANDOFF.relative_to(ROOT)),
        },
        "official_references": policy.get("official_references", {}),
        "summary": {
            "total_requirements": len(requirements),
            **counts,
            "native_source_shells_ready": (native.get("status") or {}).get("native_ui_shells_ready") is True,
            "native_store_submission_ready": (native.get("status") or {}).get("native_store_submission_ready") is True,
            "public_urls_ready": all(_public_https(value) for value in (packet.get("public_urls") or {}).values()),
            "evidence_complete": bool(evidence.get("release_evidence_complete")),
            "policy_sources_checked_on": policy.get("sources_checked_on", ""),
            "policy_source_age_days": _policy_source_age_days(policy.get("sources_checked_on")),
            "policy_sources_fresh": _policy_sources_fresh(policy.get("sources_checked_on")),
        },
        "requirements": requirements,
        "external_blockers": packet.get("known_external_blockers_before_submission", []),
    }
    return _redact_payload(matrix)


def render_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix["summary"]
    lines = [
        "# Thought Pins Store Readiness Matrix",
        "",
        f"Generated: {matrix['generated_at_utc']}",
        f"Source evidence: `{matrix.get('source_evidence') or 'none'}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Requirements", ""])
    for item in matrix["requirements"]:
        lines.append(f"### {item['id']}")
        lines.append(f"- Platform: `{item['platform']}`")
        lines.append(f"- Readiness: `{item['readiness']}`")
        lines.append(f"- Implementation status: `{item['implementation_status']}`")
        lines.append(f"- Official reference: `{item['official_reference_url']}`")
        if item.get("evidence_steps"):
            step_text = ", ".join(f"{step['name']}={step['status']}" for step in item["evidence_steps"])
            lines.append(f"- Evidence steps: {step_text}")
        missing_refs = [ref["ref"] for ref in item.get("evidence_refs", []) if ref["status"] == "missing"]
        if missing_refs:
            lines.append(f"- Missing repo evidence: {', '.join(missing_refs)}")
        if item.get("native_review_flows"):
            lines.append(f"- Native flow coverage: {', '.join(item['native_review_flows'])}")
        lines.append("")
    lines.extend(["## External Store/Account Tasks", ""])
    for blocker in matrix.get("external_blockers") or []:
        lines.append(f"- {blocker}")
    lines.append("")
    return "\n".join(lines)


def _policy_source_age_days(value: object) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return (date.today() - date.fromisoformat(value)).days
    except ValueError:
        return None


def _policy_sources_fresh(value: object) -> bool:
    age_days = _policy_source_age_days(value)
    return age_days is not None and 0 <= age_days <= POLICY_SOURCE_MAX_AGE_DAYS


def _gate_for(
    requirement: dict[str, Any], apple_gates: dict[str, dict[str, Any]], google_gates: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    gate_name = requirement.get("local_gate")
    if gate_name in apple_gates:
        return apple_gates[gate_name]
    if gate_name in google_gates:
        return google_gates[gate_name]
    return {}


def _native_flow_index(flows: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for flow in flows:
        flow_id = str(flow.get("id") or "")
        for req_id in flow.get("store_relevance") or []:
            result.setdefault(str(req_id), []).append(flow_id)
    return result


def _step_statuses(req_id: str, steps: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    statuses = []
    for name in REQUIREMENT_STEP_MAP.get(req_id, []):
        step = steps.get(name)
        statuses.append(
            {
                "name": name,
                "status": str(step.get("status") if step else "missing"),
                "reason": str(step.get("reason") if step else "not present in evidence"),
            }
        )
    return statuses


def _evidence_ref_status(ref: Any) -> dict[str, str]:
    value = str(ref)
    if value.startswith("https://"):
        return {"ref": value, "status": "external_url" if _public_https(value) else "invalid_url"}
    if value.startswith("/") or re.match(r"^(GET|POST|DELETE|PATCH|PUT)\s+/", value):
        return {"ref": value, "status": "api_contract_marker"}
    path = ROOT / value
    if path.is_file() or path.is_dir():
        return {"ref": value, "status": "present"}
    return {"ref": value, "status": "missing"}


def _requirement_status(
    implementation_status: str,
    repo_refs: list[dict[str, str]],
    step_refs: list[dict[str, str]],
    has_evidence: bool,
) -> str:
    if any(ref["status"] in {"missing", "invalid_url"} for ref in repo_refs):
        return "code_gap_missing_evidence"
    if any(marker in implementation_status for marker in EXTERNAL_STATUS_MARKERS):
        return "code_ready_needs_external_setup"
    if not has_evidence:
        return "code_ready_needs_evidence"
    if any(step["status"] in {"failed", "blocked"} for step in step_refs):
        return "blocked_by_current_evidence"
    if any(step["status"] in {"missing", "skipped"} for step in step_refs):
        return "code_ready_needs_evidence"
    return "locally_proven"


def _count_readiness(requirements: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "locally_proven": 0,
        "code_ready_needs_external_setup": 0,
        "code_ready_needs_evidence": 0,
        "blocked_by_current_evidence": 0,
        "code_gap_missing_evidence": 0,
    }
    for item in requirements:
        readiness = item.get("readiness")
        if readiness in counts:
            counts[readiness] += 1
    return counts


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _stamp_from_evidence(evidence: dict[str, Any], evidence_file: Path | None) -> str:
    if evidence_file:
        match = re.search(r"(\d{8}T\d{6}Z)", evidence_file.name)
        if match:
            return match.group(1)
    generated = str(evidence.get("generated_at_utc", ""))
    digits = re.sub(r"[^0-9]", "", generated)[:14]
    if len(digits) >= 14:
        return f"{digits[:8]}T{digits[8:14]}Z"
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _dedupe(values: list[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _public_https(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.hostname not in {"localhost", "127.0.0.1"}


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
