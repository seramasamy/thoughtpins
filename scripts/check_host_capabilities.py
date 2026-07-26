"""Record host capabilities needed for closed-beta proof.

This does not certify the product by itself. It tells the next operator whether
this machine can run the external proof gates: Docker Compose/RLS, Playwright
browser screenshots, native toolchains, and staging smoke commands. Missing or
blocked tools are reported as host limitations unless --strict is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FRONTEND = ROOT / "frontend"

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

REQUIRED_FOR_PUBLIC_BETA = {"docker_daemon", "docker_compose_config", "playwright_browser_smoke"}
REQUIRED_FOR_NATIVE_SUBMISSION = {"swift_toolchain", "android_gradle_or_wrapper", "java_toolchain"}


MISSING_MARKERS = {
    "executable doesn't exist": "Playwright browser binary is missing.",
    "please run the following command to download new browsers": "Playwright browser binary is missing.",
}
BLOCKER_MARKERS = {
    "spawn eperm": "Host blocks child-process/browser spawn.",
    "docker client must be run with elevated privileges": "Docker client needs elevated privileges on this host.",
    "cannot connect to the docker daemon": "Docker daemon is not reachable.",
    "is the docker daemon running": "Docker daemon is not reachable.",
    "error during connect": "Docker daemon is not reachable.",
    "the system cannot find the file specified": "Required executable or browser binary is missing.",
}


@dataclass
class Capability:
    id: str
    label: str
    status: str
    required_for: list[str]
    command: list[str] = field(default_factory=list)
    detail: str = ""
    remediation: str = ""


@dataclass
class HostCapabilityReport:
    app: str = "Thought Pins"
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    platform: str = sys.platform
    cwd: str = ROOT.name
    capabilities: list[Capability] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    report_path: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Check host capabilities for Thought Pins closed-beta proof.")
    parser.add_argument(
        "--strict", action="store_true", help="Exit non-zero if public-beta proof capabilities are blocked or missing."
    )
    parser.add_argument(
        "--with-browser-smoke",
        action="store_true",
        help="Attempt a real Playwright Chromium launch probe instead of only listing tests.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument(
        "--output", default="", help="Optional output JSON path. Defaults to reports/host-capabilities-*.json."
    )
    args = parser.parse_args()

    report = build_report(with_browser_smoke=args.with_browser_smoke)
    _write_report(report, args.output)
    payload = report_payload(report)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_summary(payload)
    return 1 if args.strict and not payload["public_beta_host_ready"] else 0


def build_report(*, with_browser_smoke: bool = False) -> HostCapabilityReport:
    report = HostCapabilityReport()
    report.capabilities.extend(
        [
            _tool_version("python", "Python", [sys.executable, "--version"], required_for=["local_acceptance"]),
            _tool_version("node", "Node.js", ["node", "--version"], required_for=["web_build", "playwright"]),
            _tool_version("npm", "npm", ["npm", "--version"], required_for=["web_build", "playwright"]),
            _docker_daemon_capability(),
            _docker_compose_capability(),
            _playwright_capability(with_browser_smoke=with_browser_smoke),
            _tool_version(
                "swift_toolchain",
                "Swift toolchain",
                ["swift", "--version"],
                required_for=["native_ios_submission"],
                missing_status="missing",
            ),
            _java_capability(),
            _android_gradle_capability(),
        ]
    )
    report.summary = _summary(report.capabilities)
    return report


def report_payload(report: HostCapabilityReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["public_beta_host_ready"] = _all_ready(report.capabilities, REQUIRED_FOR_PUBLIC_BETA)
    payload["native_submission_host_ready"] = _all_ready(report.capabilities, REQUIRED_FOR_NATIVE_SUBMISSION)
    return _redact_payload(payload)


def _tool_version(
    capability_id: str,
    label: str,
    command: list[str],
    *,
    required_for: list[str],
    missing_status: str = "missing",
) -> Capability:
    executable = shutil.which(command[0]) if command[0] != sys.executable else command[0]
    if not executable:
        return Capability(
            id=capability_id,
            label=label,
            status=missing_status,
            required_for=required_for,
            command=command,
            detail=f"{command[0]} is not on PATH",
            remediation=_remediation(capability_id),
        )
    resolved_command = [executable, *command[1:]]
    return _run_capability(
        capability_id,
        label,
        resolved_command,
        required_for=required_for,
        remediation=_remediation(capability_id),
        timeout=20,
    )


def _docker_daemon_capability() -> Capability:
    docker = shutil.which("docker")
    if not docker:
        return Capability(
            id="docker_daemon",
            label="Docker daemon",
            status="missing",
            required_for=["compose_rehearsal", "postgres_rls"],
            command=["docker", "version"],
            detail="docker is not on PATH",
            remediation=_remediation("docker_daemon"),
        )
    return _run_capability(
        "docker_daemon",
        "Docker daemon",
        [docker, "version"],
        required_for=["compose_rehearsal", "postgres_rls"],
        remediation=_remediation("docker_daemon"),
        timeout=30,
    )


def _docker_compose_capability() -> Capability:
    docker = shutil.which("docker")
    if not docker:
        return Capability(
            id="docker_compose_config",
            label="Docker Compose config",
            status="missing",
            required_for=["compose_rehearsal"],
            command=["docker", "compose", "config"],
            detail="docker is not on PATH",
            remediation=_remediation("docker_compose_config"),
        )
    return _run_capability(
        "docker_compose_config",
        "Docker Compose config",
        [docker, "compose", "config"],
        required_for=["compose_rehearsal"],
        remediation=_remediation("docker_compose_config"),
        timeout=60,
    )


def _playwright_capability(*, with_browser_smoke: bool) -> Capability:
    npm = shutil.which("npm")
    if not npm:
        return Capability(
            id="playwright_browser_smoke",
            label="Playwright browser smoke",
            status="missing",
            required_for=["web_screenshots", "a11y_runtime"],
            command=["npm", "run", "smoke:web"],
            detail="npm is not on PATH",
            remediation=_remediation("playwright_browser_smoke"),
        )
    if not (FRONTEND / "node_modules" / "@playwright" / "test").exists():
        return Capability(
            id="playwright_browser_smoke",
            label="Playwright browser smoke",
            status="missing",
            required_for=["web_screenshots", "a11y_runtime"],
            command=["npm", "run", "smoke:web"],
            detail="@playwright/test is not installed under frontend/node_modules",
            remediation="Run cd frontend && npm install && npm run install:playwright.",
        )
    if not with_browser_smoke:
        return _run_capability(
            "playwright_browser_smoke",
            "Playwright browser smoke",
            [npm, "run", "smoke:web", "--", "--list"],
            cwd=FRONTEND,
            required_for=["web_screenshots", "a11y_runtime"],
            remediation="Run cd frontend && npm run smoke:web on an unrestricted host for actual screenshots/a11y proof.",
            timeout=60,
            ready_status="probe_ready",
        )
    return _run_capability(
        "playwright_browser_smoke",
        "Playwright browser launch",
        ["node", "scripts/playwright-launch-probe.mjs"],
        cwd=FRONTEND,
        required_for=["web_screenshots", "a11y_runtime"],
        remediation=_remediation("playwright_browser_smoke"),
        timeout=60,
    )


def _java_capability() -> Capability:
    java = shutil.which("java")
    if not java:
        return Capability(
            id="java_toolchain",
            label="Java toolchain",
            status="missing",
            required_for=["native_android_submission"],
            command=["java", "-version"],
            detail="java is not on PATH",
            remediation=_remediation("java_toolchain"),
        )
    return _run_capability(
        "java_toolchain",
        "Java toolchain",
        [java, "-version"],
        required_for=["native_android_submission"],
        remediation=_remediation("java_toolchain"),
        timeout=20,
    )


def _android_gradle_capability() -> Capability:
    wrapper = (
        ROOT / "mobile" / "android" / "gradlew.bat" if os.name == "nt" else ROOT / "mobile" / "android" / "gradlew"
    )
    if wrapper.exists():
        return _run_capability(
            "android_gradle_or_wrapper",
            "Android Gradle wrapper",
            [str(wrapper), "--version"],
            cwd=wrapper.parent,
            required_for=["native_android_submission"],
            remediation=_remediation("android_gradle_or_wrapper"),
            timeout=60,
        )
    gradle = shutil.which("gradle")
    if gradle:
        return _run_capability(
            "android_gradle_or_wrapper",
            "Android Gradle",
            [gradle, "--version"],
            required_for=["native_android_submission"],
            remediation=_remediation("android_gradle_or_wrapper"),
            timeout=60,
        )
    return Capability(
        id="android_gradle_or_wrapper",
        label="Android Gradle wrapper or Gradle",
        status="missing",
        required_for=["native_android_submission"],
        command=["gradle", "--version"],
        detail="No mobile/android/gradlew wrapper and no gradle executable on PATH",
        remediation=_remediation("android_gradle_or_wrapper"),
    )


def _run_capability(
    capability_id: str,
    label: str,
    command: list[str],
    *,
    required_for: list[str],
    remediation: str,
    timeout: int,
    cwd: Path = ROOT,
    ready_status: str = "ready",
) -> Capability:
    started_command = [_display_command_part(part) for part in command]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_capability_env(),
        )
    except subprocess.TimeoutExpired:
        return Capability(
            capability_id, label, "blocked", required_for, started_command, f"timed out after {timeout}s", remediation
        )
    except FileNotFoundError as exc:
        return Capability(capability_id, label, "missing", required_for, started_command, str(exc), remediation)
    combined = f"{completed.stdout}\n{completed.stderr}".strip()
    if completed.returncode == 0:
        return Capability(
            capability_id,
            label,
            ready_status,
            required_for,
            started_command,
            _success_detail(capability_id, combined),
            remediation,
        )
    status, detail = classify_failure(completed.returncode, combined)
    return Capability(capability_id, label, status, required_for, started_command, detail, remediation)


def _display_command_part(part: str) -> str:
    value = str(part)
    if any(separator in value for separator in ("/", "\\")):
        name = Path(value).name
        return _redact(name or value)
    return _redact(value)


def _success_detail(capability_id: str, output: str) -> str:
    cleaned = _clean_output(_redact(output or ""))
    if capability_id == "docker_compose_config":
        return "docker compose config parsed successfully"
    if capability_id == "playwright_browser_smoke":
        for line in cleaned.splitlines():
            if line.startswith("Total:"):
                return line.strip()
        if "browser launch completed" in cleaned.lower():
            return "Playwright browser launch completed"
        return "Playwright command completed successfully"
    if capability_id in {"node", "npm", "python", "swift_toolchain", "android_gradle_or_wrapper"}:
        return (cleaned.splitlines() or ["ready"])[0]
    if capability_id == "docker_daemon":
        return "docker daemon reachable"
    if capability_id == "java_toolchain":
        return (cleaned.splitlines() or ["java ready"])[0]
    return _tail(cleaned)


def classify_failure(returncode: int, output: str) -> tuple[str, str]:
    lowered = output.lower()
    for marker, detail in MISSING_MARKERS.items():
        if marker in lowered:
            return "missing", detail
    for marker, detail in BLOCKER_MARKERS.items():
        if marker in lowered:
            return "blocked", detail
    if returncode == 127 or "not recognized" in lowered or "no such file" in lowered:
        return "missing", "Required executable is missing."
    return "failed", f"exit code {returncode}: {_tail(output, limit=500)}"


def _summary(capabilities: list[Capability]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for capability in capabilities:
        by_status[capability.status] = by_status.get(capability.status, 0) + 1
    public_beta_missing = [
        cap.id for cap in capabilities if cap.id in REQUIRED_FOR_PUBLIC_BETA and cap.status not in {"ready"}
    ]
    native_missing = [
        cap.id for cap in capabilities if cap.id in REQUIRED_FOR_NATIVE_SUBMISSION and cap.status not in {"ready"}
    ]
    return {
        "by_status": by_status,
        "public_beta_missing_or_blocked": public_beta_missing,
        "native_submission_missing_or_blocked": native_missing,
    }


def _all_ready(capabilities: list[Capability], required: set[str]) -> bool:
    by_id = {cap.id: cap for cap in capabilities}
    return all(by_id.get(item) and by_id[item].status == "ready" for item in required)


def _write_report(report: HostCapabilityReport, output: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = (
        Path(output)
        if output
        else REPORTS / f"host-capabilities-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    report.report_path = _display_path(path)
    path.write_text(json.dumps(report_payload(report), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def _print_summary(payload: dict[str, Any]) -> None:
    print("Thought Pins host capability summary:")
    print(f"- public_beta_host_ready: {str(payload['public_beta_host_ready']).lower()}")
    print(f"- native_submission_host_ready: {str(payload['native_submission_host_ready']).lower()}")
    print(f"- report: {payload['report_path']}")
    for cap in payload["capabilities"]:
        detail = f" - {cap['detail']}" if cap.get("detail") else ""
        print(f"- {cap['id']}: {cap['status']}{detail}")


def _remediation(capability_id: str) -> str:
    return {
        "docker_daemon": "Start Docker Desktop or run from an elevated shell, then rerun .\\scripts\\run_compose_rehearsal.ps1.",
        "docker_compose_config": "Install Docker Compose v2 and rerun docker compose config from the repo root.",
        "playwright_browser_smoke": "Run cd frontend && npm run install:playwright && npm run smoke:web in an unrestricted shell or CI.",
        "swift_toolchain": "Install Xcode on macOS and run swift build from mobile/ios/ThoughtPinsApp.",
        "java_toolchain": "Install a supported JDK for Android Gradle builds.",
        "android_gradle_or_wrapper": "Add an Android Gradle wrapper/workspace or install Gradle through Android Studio/CI.",
        "node": "Install Node.js LTS and rerun frontend checks.",
        "npm": "Install npm with Node.js and rerun frontend checks.",
        "python": "Use the project virtual environment or install Python 3.13+.",
    }.get(capability_id, "Install or unblock the required host tool and rerun the capability check.")


def _capability_env() -> dict[str, str]:
    env = os.environ.copy()
    tmp = ROOT / ".tmp" / "host-capabilities"
    tmp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(tmp)
    env["TEMP"] = str(tmp)
    gradle_home = ROOT / ".gradle-local"
    android_home = ROOT / ".android-local"
    gradle_home.mkdir(parents=True, exist_ok=True)
    android_home.mkdir(parents=True, exist_ok=True)
    env["GRADLE_USER_HOME"] = str(gradle_home)
    env["ANDROID_USER_HOME"] = str(android_home)
    if os.name == "nt":
        shim = "./scripts/vite-windows-net-use-shim.cjs"
        existing = env.get("NODE_OPTIONS", "").strip()
        env["NODE_OPTIONS"] = f"{existing} --require={shim}".strip()
    return env


def _clean_output(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if not line.strip().startswith("npm notice")]
    return "\n".join(lines).strip()


def _tail(text: str, *, limit: int = 1000) -> str:
    return _redact(text or "")[-limit:]


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
