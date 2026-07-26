"""Run the closed-beta proof sequence on a Docker/browser-capable host.

This is the command to use from an elevated Windows shell, CI runner, or Linux
host when local Docker and Playwright are available. It only operates inside the
Thought Pins repo and delegates teardown to the scoped Compose rehearsal script.
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
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
REPORTS = ROOT / "reports"
COMPOSE_REPORT = REPORTS / "compose-rehearsal-latest.json"
PLAYWRIGHT_REPORT = REPORTS / "playwright-web-smoke.json"
WEB_SMOKE_DIR = REPORTS / "web-smoke"
SAFE_PROJECT_RE = re.compile(r"^thoughtpins-[a-z0-9][a-z0-9-]{0,50}$")
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
    re.compile(r"(postgresql(?:\+psycopg2)?://)([^:@/]+):([^@/]+)@"),
    re.compile(r"(redis://)(:[^@/]+@)"),
]


@dataclass(frozen=True)
class ProofStep:
    name: str
    command: list[str]
    cwd: Path = ROOT
    timeout: int = 900
    required: bool = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Thought Pins closed-beta host proof.")
    parser.add_argument(
        "--project-name",
        default="thoughtpins-rehearsal",
        help="Scoped Compose project name; must start with thoughtpins-.",
    )
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip generated scratch cleanup before proof.")
    parser.add_argument("--skip-compose", action="store_true", help="Skip Docker Compose rehearsal.")
    parser.add_argument(
        "--keep-compose-running", action="store_true", help="Leave the scoped Compose project running after rehearsal."
    )
    parser.add_argument(
        "--skip-playwright-install", action="store_true", help="Do not run Playwright browser install before web smoke."
    )
    parser.add_argument("--skip-playwright", action="store_true", help="Skip Playwright browser smoke/screenshots.")
    parser.add_argument("--full-tests", action="store_true", help="Run full tests inside the final evidence collector.")
    parser.add_argument(
        "--no-strict-complete", action="store_true", help="Do not require strict-complete evidence at the end."
    )
    args = parser.parse_args(argv)

    _assert_repo_root(ROOT)
    _assert_safe_project_name(args.project_name)
    REPORTS.mkdir(parents=True, exist_ok=True)

    py = _python_executable()
    npm = _required_tool("npm")
    docker = _required_tool("docker")

    steps: list[ProofStep] = []
    if not args.skip_cleanup:
        steps.append(
            ProofStep(
                "cleanup generated scratch artifacts",
                [py, "scripts/clean_local_artifacts.py", "--apply"],
                timeout=120,
                required=False,
            )
        )
    if not args.skip_compose:
        steps.append(ProofStep("Docker daemon preflight", [docker, "version"], timeout=30))
    if not args.skip_playwright and not args.skip_playwright_install:
        steps.append(
            ProofStep(
                "install Playwright Chromium",
                [npm, "run", "install:playwright"],
                cwd=FRONTEND,
                timeout=900,
                required=False,
            )
        )
    preflight = [py, "scripts/check_host_capabilities.py", "--strict"]
    if not args.skip_playwright:
        preflight.append("--with-browser-smoke")
    steps.append(ProofStep("strict host capability preflight", preflight, timeout=180))
    if not args.skip_compose:
        compose = [
            py,
            "scripts/run_compose_rehearsal.py",
            "--project-name",
            args.project_name,
            "--report-path",
            str(COMPOSE_REPORT.relative_to(ROOT)),
        ]
        if args.keep_compose_running:
            compose.append("--keep-running")
        steps.append(ProofStep("Docker Compose rehearsal with RLS and backup", compose, timeout=1800))
    if not args.skip_playwright:
        steps.append(
            ProofStep("Playwright web smoke and screenshots", [npm, "run", "smoke:web"], cwd=FRONTEND, timeout=300)
        )
    steps.append(
        ProofStep(
            "external proof artifact validation",
            [
                py,
                "scripts/check_external_proof_artifacts.py",
                "--require-both",
                "--compose-report",
                str(COMPOSE_REPORT.relative_to(ROOT)),
                "--playwright-report",
                str(PLAYWRIGHT_REPORT.relative_to(ROOT)),
                "--web-smoke-dir",
                str(WEB_SMOKE_DIR.relative_to(ROOT)),
            ],
            timeout=120,
            required=not (args.skip_compose or args.skip_playwright),
        )
    )
    evidence = [
        py,
        "scripts/collect_local_closed_beta_evidence.py",
        "--telegram-api",
        "--live-article",
        "--web-smoke",
        "--compose-rehearsal-report",
        str(COMPOSE_REPORT.relative_to(ROOT)),
        "--playwright-report",
        str(PLAYWRIGHT_REPORT.relative_to(ROOT)),
        "--web-smoke-dir",
        str(WEB_SMOKE_DIR.relative_to(ROOT)),
    ]
    if args.full_tests:
        evidence.append("--full-tests")
    if not args.no_strict_complete:
        evidence.append("--strict-complete")
    steps.append(ProofStep("strict closed-beta evidence", evidence, timeout=900 if not args.full_tests else 1500))

    failed = False
    for step in steps:
        ok = _run_step(step)
        if not ok and step.required:
            failed = True
            break
    if failed:
        print("closed-beta host proof failed")
        return 1
    print("closed-beta host proof passed")
    print(f"compose report: {COMPOSE_REPORT}")
    print(f"playwright report: {PLAYWRIGHT_REPORT}")
    print(f"web screenshots: {WEB_SMOKE_DIR}")
    _print_latest_evidence_bundle()
    return 0


def _run_step(step: ProofStep) -> bool:
    started = time.perf_counter()
    print(f"\n==> {step.name}")
    print(_display_command(step.command, step.cwd))
    try:
        completed = subprocess.run(step.command, cwd=step.cwd, env=_child_env(), timeout=step.timeout, text=True)
    except subprocess.TimeoutExpired:
        print(f"failed: timed out after {step.timeout}s")
        return False
    seconds = time.perf_counter() - started
    if completed.returncode == 0:
        print(f"passed: {step.name} ({seconds:.1f}s)")
        return True
    message = f"failed: {step.name} exited {completed.returncode} ({seconds:.1f}s)"
    if step.required:
        print(message)
        return False
    print(f"warning: {message}; continuing because this step is optional")
    return True


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def _python_executable() -> str:
    local = ROOT / ".venv" / "Scripts" / "python.exe"
    if local.is_file():
        return str(local)
    return sys.executable


def _required_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required tool is not on PATH: {name}")
    return path


def _assert_repo_root(root: Path) -> None:
    expected = {"src", "scripts", "frontend", "docker-compose.yml", "pyproject.toml"}
    missing = sorted(item for item in expected if not (root / item).exists())
    if missing:
        raise RuntimeError(f"Refusing to run outside Thought Pins repo; missing {missing}")


def _assert_safe_project_name(name: str) -> None:
    if not SAFE_PROJECT_RE.fullmatch(name):
        raise ValueError(
            "Compose project name must be scoped as thoughtpins-* so teardown cannot target unrelated projects."
        )


def _display_command(command: list[str], cwd: Path) -> str:
    rel = cwd.relative_to(ROOT) if cwd != ROOT else Path(".")
    return f"cwd={rel.as_posix()} $ " + " ".join(_redact(part) for part in command)


def _print_latest_evidence_bundle() -> None:
    evidence_path = _latest_report("closed-beta-evidence-*.json")
    if not evidence_path:
        print("evidence bundle: no closed-beta evidence report found")
        return
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"evidence bundle: unable to read {evidence_path}: {exc}")
        return

    print("evidence bundle:")
    for label, key in (
        ("evidence", "report_path"),
        ("gap report", "gap_report_path"),
        ("launch packet", "launch_packet_path"),
        ("objective audit", "objective_audit_path"),
        ("store readiness matrix", "store_readiness_matrix_path"),
    ):
        value = payload.get(key)
        if value:
            print(f"  {label}: {_redact(str(value))}")


def _latest_report(pattern: str) -> Path | None:
    matches = [path for path in REPORTS.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(postgresql"):
            redacted = pattern.sub(r"\1***:***@", redacted)
        elif pattern.pattern.startswith("(redis"):
            redacted = pattern.sub(r"\1***@", redacted)
        elif "Bearer" in pattern.pattern:
            redacted = pattern.sub(r"\1***", redacted)
        else:
            redacted = pattern.sub("***", redacted)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
