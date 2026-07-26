"""Validate the generated store-readiness matrix contract."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from generate_store_readiness_matrix import build_store_readiness_matrix, write_store_readiness_matrix  # noqa: E402

STORE_PACKET = ROOT / "deploy" / "store" / "submission-packet.json"
POLICY_REQUIREMENTS = ROOT / "deploy" / "store" / "store-policy-requirements.json"
NATIVE_HANDOFF = ROOT / "deploy" / "store" / "native-review-handoff.json"

REQUIRED_REQUIREMENT_IDS = {
    "apple_review_access",
    "apple_live_backend",
    "apple_privacy_policy_and_retention",
    "apple_in_app_account_deletion",
    "apple_sign_in_with_apple_parity",
    "apple_ai_disclosure_and_safety_reporting",
    "apple_user_generated_content_safety_controls",
    "google_privacy_policy",
    "google_data_safety",
    "google_in_app_account_deletion",
    "google_web_account_deletion",
    "google_secure_handling_and_no_sale",
    "google_ai_generated_content_safety",
    "public_build_no_founder_leakage",
}
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Thought Pins store-readiness matrix generation.")
    parser.add_argument("--evidence", default="", help="Optional evidence JSON to validate against.")
    parser.add_argument("--self-test", action="store_true", help="Generate and validate a synthetic matrix in .tmp.")
    args = parser.parse_args()

    failures: list[str] = []
    packet = _load_json(STORE_PACKET, failures)
    policy = _load_json(POLICY_REQUIREMENTS, failures)
    native = _load_json(NATIVE_HANDOFF, failures)
    if not packet or not policy or not native:
        return _finish(failures)

    evidence = (
        _synthetic_evidence()
        if args.self_test
        else (_load_json(Path(args.evidence), failures) if args.evidence else {})
    )
    if failures:
        return _finish(failures)

    try:
        matrix = build_store_readiness_matrix(
            evidence, packet, policy, native, evidence_file=Path(args.evidence) if args.evidence else None
        )
    except Exception as exc:
        failures.append(f"store readiness matrix generation failed: {exc}")
        return _finish(failures)

    _check_matrix(matrix, packet, policy, native, failures)
    _check_writer(failures) if args.self_test else None
    _check_no_secrets(json.dumps(matrix), failures)
    return _finish(failures)


def _check_matrix(matrix: dict, packet: dict, policy: dict, native: dict, failures: list[str]) -> None:
    if matrix.get("app") != "Thought Pins":
        failures.append("matrix app must be Thought Pins")
    refs = matrix.get("official_references") or {}
    for key, value in refs.items():
        if not _public_https(str(value)):
            failures.append(f"official reference {key} must be a public HTTPS URL")
    requirements = matrix.get("requirements") or []
    by_id = {item.get("id"): item for item in requirements}
    missing = REQUIRED_REQUIREMENT_IDS - by_id.keys()
    if missing:
        failures.append(f"matrix missing requirements: {sorted(missing)}")
    extra = by_id.keys() - REQUIRED_REQUIREMENT_IDS
    if extra:
        failures.append(f"matrix has unexpected requirements: {sorted(extra)}")

    allowed_readiness = {
        "locally_proven",
        "code_ready_needs_external_setup",
        "code_ready_needs_evidence",
        "blocked_by_current_evidence",
        "code_gap_missing_evidence",
    }
    for item in requirements:
        if item.get("readiness") not in allowed_readiness:
            failures.append(f"requirement {item.get('id')} has invalid readiness {item.get('readiness')}")
        if not item.get("official_reference_url"):
            failures.append(f"requirement {item.get('id')} missing official_reference_url")
        if item.get("readiness") == "code_gap_missing_evidence":
            failures.append(f"requirement {item.get('id')} has missing repo evidence")
        if not item.get("evidence_refs"):
            failures.append(f"requirement {item.get('id')} must have evidence_refs")

    summary = matrix.get("summary") or {}
    if summary.get("total_requirements") != len(REQUIRED_REQUIREMENT_IDS):
        failures.append("summary.total_requirements must match required requirement count")
    if summary.get("native_source_shells_ready") is not True:
        failures.append("matrix should report native source shells ready from native handoff")
    if summary.get("native_store_submission_ready") is not False:
        failures.append("matrix must keep native store submission false until signed/device evidence exists")
    if summary.get("public_urls_ready") is not True:
        failures.append("matrix public URLs should be public HTTPS values")
    if not matrix.get("external_blockers"):
        failures.append("matrix must preserve external store/account blockers")

    packet_refs = packet.get("official_references") or {}
    policy_refs = policy.get("official_references") or {}
    if refs != policy_refs or refs != packet_refs:
        failures.append("matrix official references must match policy and submission packets")
    if not (native.get("required_review_flows") or []):
        failures.append("native handoff must include required_review_flows")


def _check_writer(failures: list[str]) -> None:
    tmp = ROOT / ".tmp" / f"store-readiness-check-{secrets.token_hex(6)}"
    try:
        tmp.mkdir(parents=True, exist_ok=False)
        result = write_store_readiness_matrix(None, output_dir=tmp)
        markdown = Path(result["markdown_path"])
        json_path = Path(result["json_path"])
        if not markdown.is_file() or not json_path.is_file():
            failures.append("store readiness matrix writer did not create Markdown and JSON")
        else:
            text = markdown.read_text(encoding="utf-8") + json_path.read_text(encoding="utf-8")
            if "Thought Pins Store Readiness Matrix" not in text:
                failures.append("store readiness matrix writer output missing title")
            _check_no_secrets(text, failures)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _synthetic_evidence() -> dict:
    passed_steps = [
        "quick release gate",
        "review account packet",
        "review notes packet",
        "store submission packet",
        "app store compliance",
        "public export hygiene",
        "production parity",
        "startup shutdown smoke",
        "runtime feature smoke",
        "domain readiness",
    ]
    return {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "release_evidence_complete": False,
        "steps": [{"name": name, "status": "passed", "seconds": 0.1, "command": []} for name in passed_steps],
    }


def _load_json(path: Path, failures: list[str]) -> dict:
    if not path.is_file():
        failures.append(f"missing JSON file: {path.relative_to(ROOT)}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        failures.append(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}


def _public_https(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.hostname not in {"localhost", "127.0.0.1"}


def _check_no_secrets(text: str, failures: list[str]) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append("store readiness matrix contains secret-like material")
            return


def _finish(failures: list[str]) -> int:
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Store readiness matrix check failed: {len(failures)} failure(s).")
        return 1
    print("Store readiness matrix check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
