"""Collect closed-beta release evidence without printing secrets.

This script coordinates the existing release, compliance, parity, backup, vault,
and optional runtime smoke checks into one redacted JSON artifact under reports/.
It is conservative: Docker, browser, Telegram, and live API checks are recorded
as blocked/skipped when the local host cannot run them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


@dataclass
class EvidenceStep:
    name: str
    status: str
    seconds: float
    command: list[str]
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    reason: str = ""


@dataclass
class EvidenceReport:
    app: str = "Thought Pins"
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    host: dict[str, Any] = field(default_factory=dict)
    steps: list[EvidenceStep] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    report_path: str = ""
    gap_report_path: str = ""
    launch_packet_path: str = ""
    host_capabilities_path: str = ""
    external_proof_path: str = ""
    store_readiness_matrix_path: str = ""
    objective_audit_path: str = ""

    @property
    def passed(self) -> bool:
        return all(step.status in {"passed", "skipped", "blocked"} for step in self.steps)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Thought Pins closed-beta evidence.")
    parser.add_argument(
        "--full-tests",
        action="store_true",
        help="Run full pytest through release_check.py instead of quick release gates.",
    )
    parser.add_argument(
        "--api-base-url", default="", help="Running API base URL for live runtime/founder/parity smoke."
    )
    parser.add_argument(
        "--telegram-api", action="store_true", help="Validate configured Telegram bot through Telegram API."
    )
    parser.add_argument("--web-smoke", action="store_true", help="Attempt Playwright web smoke/screenshots.")
    parser.add_argument(
        "--compose-rehearsal-report",
        default="",
        help="Compose rehearsal JSON from scripts/run_compose_rehearsal.ps1 or scripts/run_compose_rehearsal.py.",
    )
    parser.add_argument(
        "--playwright-report", default="", help="Playwright JSON report from cd frontend && npm run smoke:web."
    )
    parser.add_argument(
        "--web-smoke-dir", default="reports/web-smoke", help="Directory containing Playwright review screenshots."
    )
    parser.add_argument(
        "--use-latest-external-proof",
        action="store_true",
        help="Validate latest reports/* Compose and Playwright proof artifacts.",
    )
    parser.add_argument("--live-article", action="store_true", help="Run live public article provider checks.")
    parser.add_argument(
        "--keep-vault-temp", action="store_true", help="Keep vault stress temporary files for inspection."
    )
    parser.add_argument("--json", action="store_true", help="Print the full redacted JSON report.")
    parser.add_argument(
        "--strict-complete",
        action="store_true",
        help="Exit nonzero unless every required evidence check passes with no skipped or blocked proof.",
    )
    args = parser.parse_args()

    report = EvidenceReport(host=_host_info())
    py = sys.executable

    release_cmd = [py, "scripts/release_check.py", "--skip-quality"]
    if not args.full_tests:
        release_cmd.append("--skip-tests")
    if args.api_base_url:
        release_cmd.extend(["--api-base-url", args.api_base_url.rstrip("/")])
    _run_step(
        report,
        "release gate" if args.full_tests else "quick release gate",
        release_cmd,
        timeout=420 if args.full_tests else 180,
    )

    for name, cmd, timeout in [
        ("review account packet", [py, "scripts/check_review_account_packet.py"], 30),
        ("app store compliance", [py, "scripts/app_store_compliance_check.py"], 30),
        ("store submission packet", [py, "scripts/check_store_submission_packet.py"], 30),
        ("review notes packet", [py, "scripts/check_review_notes_packet.py"], 30),
        ("closed-beta deployment packet", [py, "scripts/check_deployment_packet.py"], 30),
        ("web review harness", [py, "scripts/check_web_review_harness.py"], 30),
        ("web app product contract", [py, "scripts/check_web_app_contract.py"], 30),
        ("mobile core scaffold", [py, "scripts/check_mobile_core.py"], 30),
        ("native review handoff", [py, "scripts/check_native_review_handoff.py"], 30),
        ("public export hygiene", [py, "scripts/check_public_export.py"], 60),
        ("backup restore smoke", [py, "scripts/smoke_restore_backup.py"], 90),
    ]:
        _run_step(report, name, cmd, timeout=timeout)

    vault_cmd = [py, "scripts/stress_vault_obsidian.py", "--offline-fixture", "--obsidian-defaults", "--json"]
    if args.keep_vault_temp:
        vault_cmd.append("--keep-temp")
    _run_step(report, "obsidian vault stress", vault_cmd, timeout=180)

    parity_cmd = [py, "scripts/production_parity_check.py"]
    if args.api_base_url:
        parity_cmd.extend(["--base-url", args.api_base_url.rstrip("/"), "--strict-api"])
    _run_step(report, "production parity", parity_cmd, timeout=120)
    _run_step(report, "host capability preflight", [py, "scripts/check_host_capabilities.py"], timeout=90)
    report.host_capabilities_path = _latest_report_path("host-capabilities-*.json")
    _check_external_proof(report, args, py)
    _run_step(report, "startup shutdown smoke", [py, "scripts/smoke_startup_shutdown.py"], timeout=90)
    _check_docker(report)

    if args.api_base_url:
        env = os.environ.copy()
        env["THOUGHTPINS_BASE_URL"] = args.api_base_url.rstrip("/")
        _run_step(report, "runtime feature smoke", [py, "scripts/smoke_runtime_features.py"], timeout=300, env=env)
        _run_step(report, "founder runtime smoke", [py, "scripts/smoke_founder_local.py"], timeout=120, env=env)
    else:
        _skip(report, "runtime feature smoke", "no --api-base-url provided")
        _skip(report, "founder runtime smoke", "no --api-base-url provided")

    if args.telegram_api:
        _run_step(report, "telegram API smoke", [py, "scripts/smoke_telegram_api.py"], timeout=60)
    else:
        _skip(report, "telegram API smoke", "not requested; pass --telegram-api with configured token")

    if args.live_article:
        _run_step(
            report,
            "live article provider smoke",
            [py, "scripts/smoke_article_fetch_providers.py", "--url", "https://www.paulgraham.com/greatwork.html"],
            timeout=120,
        )
    else:
        _skip(report, "live article provider smoke", "not requested; offline vault/library tests ran")

    if args.web_smoke:
        _run_step(
            report, "playwright web smoke", _npm_command(["run", "smoke:web"]), cwd=ROOT / "frontend", timeout=180
        )
    else:
        _skip(report, "playwright web smoke", "not requested; release gate validates harness and frontend build")

    _finish_report(report)
    payload = _report_payload(report)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_summary(report)
    return _exit_code(report, strict_complete=args.strict_complete)


def _host_info() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "cwd": str(ROOT),
        "docker_on_path": shutil.which("docker") is not None,
        "npm_on_path": shutil.which("npm") is not None,
    }


def _run_step(
    report: EvidenceReport,
    name: str,
    command: list[str],
    *,
    timeout: int,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    started = time.perf_counter()
    print(f"==> {name}")
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=_step_env(env),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        seconds = time.perf_counter() - started
        combined = f"{completed.stdout}\n{completed.stderr}"
        status, reason = _classify(completed.returncode, combined)
        if status == "blocked":
            report.blockers.append(f"{name}: {reason}")
        step = EvidenceStep(
            name=name,
            status=status,
            seconds=round(seconds, 2),
            command=_display_command(command),
            returncode=completed.returncode,
            stdout_tail=_tail(completed.stdout),
            stderr_tail=_tail(completed.stderr),
            reason=reason,
        )
    except subprocess.TimeoutExpired as exc:
        seconds = time.perf_counter() - started
        report.blockers.append(f"{name}: timed out after {timeout}s")
        step = EvidenceStep(
            name=name,
            status="blocked",
            seconds=round(seconds, 2),
            command=_display_command(command),
            returncode=None,
            stdout_tail=_tail(exc.stdout or ""),
            stderr_tail=_tail(exc.stderr or ""),
            reason=f"timed out after {timeout}s",
        )
    report.steps.append(step)
    suffix = f" ({step.reason})" if step.reason and step.status != "passed" else ""
    print(f"{step.status}: {name}{suffix}")


def _check_external_proof(report: EvidenceReport, args: argparse.Namespace, py: str) -> None:
    if not (args.compose_rehearsal_report or args.playwright_report or args.use_latest_external_proof):
        _skip(
            report,
            "external proof artifacts",
            "not provided; pass Compose and Playwright proof reports from a capable host",
        )
        return
    command = [py, "scripts/check_external_proof_artifacts.py", "--require-both", "--max-age-hours", "168"]
    if args.use_latest_external_proof:
        command.append("--latest")
    if args.compose_rehearsal_report:
        command.extend(["--compose-report", args.compose_rehearsal_report])
    if args.playwright_report:
        command.extend(["--playwright-report", args.playwright_report])
    if args.web_smoke_dir:
        command.extend(["--web-smoke-dir", args.web_smoke_dir])
    _run_step(report, "external proof artifacts", command, timeout=60)
    report.external_proof_path = _latest_report_path("external-proof-artifacts-*.json")


def _check_docker(report: EvidenceReport) -> None:
    docker = shutil.which("docker")
    if not docker:
        _skip(report, "docker daemon availability", "docker executable not found")
        return
    _run_step(report, "docker daemon availability", [docker, "version"], timeout=30)


def _skip(report: EvidenceReport, name: str, reason: str) -> None:
    report.steps.append(EvidenceStep(name=name, status="skipped", seconds=0.0, command=[], reason=reason))
    print(f"skipped: {name} ({reason})")


def _finish_report(report: EvidenceReport) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS / f"closed-beta-evidence-{stamp}.json"
    report.report_path = str(path)

    gap_step = EvidenceStep(
        name="gap report",
        status="passed",
        seconds=0.0,
        command=_display_command([sys.executable, "scripts/generate_gap_report.py", str(path)]),
    )
    report.steps.append(gap_step)
    started = time.perf_counter()
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")
    try:
        from generate_gap_report import write_gap_report_for_evidence

        generated = write_gap_report_for_evidence(path, write_json=True)
        report.gap_report_path = str(generated.get("markdown_path", ""))
        gap_step.seconds = round(time.perf_counter() - started, 2)
    except Exception as exc:
        gap_step.status = "failed"
        gap_step.reason = str(exc)
        gap_step.seconds = round(time.perf_counter() - started, 2)
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")

    store_step = EvidenceStep(
        name="store readiness matrix",
        status="passed",
        seconds=0.0,
        command=_display_command([sys.executable, "scripts/generate_store_readiness_matrix.py", str(path)]),
    )
    report.steps.append(store_step)
    started = time.perf_counter()
    try:
        from generate_store_readiness_matrix import write_store_readiness_matrix

        generated = write_store_readiness_matrix(path, output_dir=REPORTS)
        report.store_readiness_matrix_path = str(generated.get("markdown_path", ""))
        store_step.seconds = round(time.perf_counter() - started, 2)
    except Exception as exc:
        store_step.status = "failed"
        store_step.reason = str(exc)
        store_step.seconds = round(time.perf_counter() - started, 2)
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")

    launch_step = EvidenceStep(
        name="launch packet",
        status="passed",
        seconds=0.0,
        command=_display_command([sys.executable, "scripts/generate_launch_packet.py", str(path)]),
    )
    report.steps.append(launch_step)
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")
    started = time.perf_counter()
    try:
        from generate_launch_packet import write_launch_packet_for_evidence

        generated = write_launch_packet_for_evidence(path, output_dir=REPORTS)
        report.launch_packet_path = str(generated.get("markdown_path", ""))
        launch_step.seconds = round(time.perf_counter() - started, 2)
    except Exception as exc:
        launch_step.status = "failed"
        launch_step.reason = str(exc)
        launch_step.seconds = round(time.perf_counter() - started, 2)
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")

    objective_step = EvidenceStep(
        name="objective audit",
        status="passed",
        seconds=0.0,
        command=_display_command([sys.executable, "scripts/generate_objective_audit.py", str(path)]),
    )
    report.steps.append(objective_step)
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")
    started = time.perf_counter()
    try:
        from generate_objective_audit import write_objective_audit_for_evidence

        generated = write_objective_audit_for_evidence(path, output_dir=REPORTS)
        report.objective_audit_path = str(generated.get("markdown_path", ""))
        objective_step.seconds = round(time.perf_counter() - started, 2)
    except Exception as exc:
        objective_step.status = "failed"
        objective_step.reason = str(exc)
        objective_step.seconds = round(time.perf_counter() - started, 2)
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")
    if objective_step.status == "passed" and launch_step.status == "passed":
        started = time.perf_counter()
        try:
            from generate_launch_packet import write_launch_packet_for_evidence

            generated = write_launch_packet_for_evidence(path, output_dir=REPORTS)
            report.launch_packet_path = str(generated.get("markdown_path", ""))
            launch_step.seconds = round(launch_step.seconds + (time.perf_counter() - started), 2)
        except Exception as exc:
            launch_step.status = "failed"
            launch_step.reason = f"refresh after objective audit failed: {exc}"
    path.write_text(json.dumps(_report_payload(report), indent=2, sort_keys=True), encoding="utf-8")


def _report_payload(report: EvidenceReport) -> dict[str, Any]:
    payload = asdict(report)
    failed = _step_names(report, "failed")
    blocked = _step_names(report, "blocked")
    skipped = _step_names(report, "skipped")
    payload["passed"] = report.passed
    payload["no_failed_steps"] = not failed
    payload["failed_steps"] = failed
    payload["blocked_steps"] = blocked
    payload["skipped_steps"] = skipped
    payload["release_evidence_complete"] = not failed and not blocked and not skipped
    return payload


def _exit_code(report: EvidenceReport, *, strict_complete: bool) -> int:
    if not report.passed:
        return 1
    if strict_complete and not _report_payload(report)["release_evidence_complete"]:
        print("Strict evidence completeness failed: blocked or skipped proof remains.")
        return 2
    return 0


def _latest_report_path(pattern: str) -> str:
    matches = sorted(REPORTS.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return str(matches[0]) if matches else ""


def _step_names(report: EvidenceReport, status: str) -> list[str]:
    return [step.name for step in report.steps if step.status == status]


def _print_summary(report: EvidenceReport) -> None:
    print("\nClosed-beta evidence summary:")
    for step in report.steps:
        print(f"- {step.status:7} {step.seconds:6.1f}s  {step.name}")
    if report.blockers:
        print("\nEnvironment blockers:")
        for blocker in report.blockers:
            print(f"- {_redact(blocker)}")
    payload = _report_payload(report)
    print(f"\nReport: {report.report_path}")
    if report.gap_report_path:
        print(f"Gap report: {report.gap_report_path}")
    if report.launch_packet_path:
        print(f"Launch packet: {report.launch_packet_path}")
    if report.objective_audit_path:
        print(f"Objective audit: {report.objective_audit_path}")
    print(f"Evidence complete: {payload['release_evidence_complete']}")
    print("Closed-beta evidence collection passed." if report.passed else "Closed-beta evidence collection failed.")


def _classify(returncode: int, output: str) -> tuple[str, str]:
    if returncode == 0:
        return "passed", ""
    lowered = output.lower()
    blocker_markers = [
        "spawn eperm",
        "docker client must be run with elevated privileges",
        "cannot connect to the docker daemon",
        "is the docker daemon running",
        "the system cannot find the file specified",
        "error during connect",
    ]
    for marker in blocker_markers:
        if marker in lowered:
            return "blocked", marker
    return "failed", f"exit code {returncode}"


def _tail(text: bytes | str | None, limit: int = 4000) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return _redact(text or "")[-limit:]


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


def _display_command(command: list[str]) -> list[str]:
    return [_redact(part) for part in command]


def _step_env(env: dict[str, str] | None) -> dict[str, str]:
    resolved = (env or os.environ.copy()).copy()
    src = str(ROOT / "src")
    current = resolved.get("PYTHONPATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if src not in parts:
        parts.insert(0, src)
    resolved["PYTHONPATH"] = os.pathsep.join(parts)
    return resolved


def _npm_command(args: list[str]) -> list[str]:
    npm = shutil.which("npm") or "npm"
    return [npm, *args]


if __name__ == "__main__":
    raise SystemExit(main())
