"""Cross-platform Docker Compose production rehearsal for Thought Pins.

This mirrors ``scripts/run_compose_rehearsal.ps1`` for Linux/macOS/CI hosts
that have Docker Compose but not PowerShell. It starts only a scoped Compose
project, runs the same live API/RLS/backup checks, writes the same portable
``reports/compose-rehearsal-*.json`` artifact, and tears down only that project
unless ``--keep-running`` is supplied.
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
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SAFE_PROJECT_RE = re.compile(r"^thoughtpins-[a-z0-9][a-z0-9-]{0,50}$")
SAFE_WSL_DISTRO_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DEFAULT_PROJECT_NAME = "thoughtpins-rehearsal"
DEFAULT_BASE_URL = "http://127.0.0.1:8420"
DEFAULT_WEB_URL = "http://127.0.0.1:8421/app"
DEFAULT_OWNER_DB_URL = "postgresql+psycopg2://thoughtpins:thoughtpins@127.0.0.1:5432/thoughtpins"
DEFAULT_APP_DB_URL = "postgresql+psycopg2://thoughtpins_app:thoughtpins_app@127.0.0.1:5432/thoughtpins"
CHECK_MARKERS = [
    "docker compose config",
    "compose up api web worker postgres redis qdrant migrate",
    "GET /health",
    "web smoke GET /app",
    "production_parity_check.py --strict-api --with-postgres-rls",
    "smoke_api.py",
    "smoke_restore_backup.py",
]
SECRET_PATTERNS = [
    re.compile(r"(postgresql(?:\+psycopg2)?://)([^:@/]+):([^@/]+)@"),
    re.compile(r"(redis://)(:[^@/]+@)"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
]


@dataclass
class StepResult:
    name: str
    status: str
    seconds: float
    detail: str = ""


@dataclass
class RehearsalReport:
    app: str = "Thought Pins"
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "running"
    project_name: str = DEFAULT_PROJECT_NAME
    keep_running: bool = False
    skip_build: bool = False
    started_at_utc: str = ""
    finished_at_utc: str = ""
    stopped_compose_project: bool = False
    base_url: str = DEFAULT_BASE_URL
    checks: list[str] = field(default_factory=lambda: list(CHECK_MARKERS))
    steps: list[StepResult] = field(default_factory=list)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Docker Compose closed-beta production rehearsal.")
    parser.add_argument(
        "--keep-running", action="store_true", help="Leave the scoped Compose project running after checks."
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Use existing images instead of docker compose up --build."
    )
    parser.add_argument(
        "--health-timeout-seconds", type=int, default=180, help="Maximum seconds to wait for API health."
    )
    parser.add_argument(
        "--project-name",
        default=DEFAULT_PROJECT_NAME,
        help="Scoped Compose project name; must start with thoughtpins-.",
    )
    parser.add_argument("--report-path", default="", help="Optional deterministic JSON report path.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Local API base URL exposed by Compose.")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL, help="Local web URL exposed by Compose.")
    parser.add_argument(
        "--owner-db-url", default=DEFAULT_OWNER_DB_URL, help="Migration/owner PostgreSQL URL for RLS fixture setup."
    )
    parser.add_argument(
        "--app-db-url", default=DEFAULT_APP_DB_URL, help="Non-owner app-role PostgreSQL URL for RLS verification."
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable used for repo smoke scripts.")
    parser.add_argument(
        "--wsl-distro",
        default="",
        help="On Windows, run Docker through this WSL distribution as root instead of Docker Desktop.",
    )
    args = parser.parse_args()

    assert_safe_compose_project_name(args.project_name)
    runner = ComposeRehearsal(args)
    return runner.run()


class ComposeRehearsal:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.started_at = datetime.now(timezone.utc)
        self.report = RehearsalReport(
            project_name=args.project_name,
            keep_running=bool(args.keep_running),
            skip_build=bool(args.skip_build),
            started_at_utc=self.started_at.isoformat(),
            base_url=args.base_url.rstrip("/"),
        )
        self.stopped_compose_project = False
        self.docker = docker_command(args.wsl_distro)

    def run(self) -> int:
        status = "failed"
        try:
            self._step("docker daemon", lambda: self._run([*self.docker, "info"]))
            self._step("docker compose config", lambda: self._compose(["config", "--quiet"]))
            self._step("start compose services", self._start_services)
            self._step(
                "wait for API health",
                lambda: wait_for_health(f"{self.report.base_url}/health", self.args.health_timeout_seconds),
            )
            self._step("web smoke", self._web_smoke)
            smoke_env = self._smoke_env()
            self._step(
                "production parity with live API and RLS",
                lambda: self._run(
                    [
                        self.args.python,
                        "scripts/production_parity_check.py",
                        "--base-url",
                        self.report.base_url,
                        "--strict-api",
                        "--with-postgres-rls",
                    ],
                    env=smoke_env,
                ),
            )
            self._step("HTTP API smoke", lambda: self._run([self.args.python, "scripts/smoke_api.py"], env=smoke_env))
            self._step(
                "backup restore smoke",
                lambda: self._run([self.args.python, "scripts/smoke_restore_backup.py"], env=smoke_env),
            )
            status = "passed"
            print("compose rehearsal passed")
            return 0
        except Exception as exc:
            print(f"compose rehearsal failed: {_redact(str(exc))}", file=sys.stderr)
            return 1
        finally:
            if not self.args.keep_running:
                print(f"==> stop compose project {self.args.project_name}")
                try:
                    self._compose(["down"])
                    self.stopped_compose_project = True
                except Exception as exc:
                    print(
                        f"warning: failed to stop compose project {self.args.project_name}: {_redact(str(exc))}",
                        file=sys.stderr,
                    )
            else:
                print(f"compose project {self.args.project_name} left running because --keep-running was supplied")
            self._write_report(status)

    def _step(self, name: str, fn) -> None:
        started = time.perf_counter()
        print(f"==> {name}")
        try:
            fn()
        except Exception as exc:
            seconds = round(time.perf_counter() - started, 2)
            self.report.steps.append(StepResult(name=name, status="failed", seconds=seconds, detail=_redact(str(exc))))
            raise
        seconds = round(time.perf_counter() - started, 2)
        self.report.steps.append(StepResult(name=name, status="passed", seconds=seconds))
        print(f"ok: {name}")

    def _start_services(self) -> None:
        args = ["up", "-d"]
        if not self.args.skip_build:
            args.append("--build")
        args.extend(["postgres", "redis", "qdrant", "migrate", "api", "web", "worker"])
        self._compose(args)

    def _web_smoke(self) -> None:
        deadline = time.time() + self.args.health_timeout_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(self.args.web_url, timeout=10) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    if response.status == 200 and "Thought Pins" in body:
                        return
                    last_error = f"unexpected status/body from {self.args.web_url}"
            except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
                last_error = str(exc)
            time.sleep(2)
        raise TimeoutError(f"Timed out waiting for web smoke at {self.args.web_url}: {_redact(last_error)}")

    def _compose(self, args: list[str]) -> None:
        self._run([*self.docker, "compose", "-p", self.args.project_name, *args])

    def _run(self, command: list[str], *, env: dict[str, str] | None = None) -> None:
        completed = subprocess.run(command, cwd=ROOT, env=env, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"{_display_command(command)} failed with exit code {completed.returncode}")

    def _smoke_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(ROOT / "src"),
                "DATABASE_URL": self.args.owner_db_url,
                "RLS_VERIFY_DATABASE_URL": self.args.app_db_url,
                "THOUGHTPINS_BASE_URL": self.report.base_url,
                "THOUGHTPINS_SMOKE_WAIT_JOB": "true",
                "THOUGHTPINS_SMOKE_SEED_LOCAL": "true",
                "THOUGHTPINS_SMOKE_HTTP_TIMEOUT_SECONDS": "90",
                "THOUGHTPINS_API_KEY": os.getenv(
                    "THOUGHTPINS_COMPOSE_API_KEY",
                    "change-me-for-local-compose-api-key-32chars",
                ),
            }
        )
        return env

    def _write_report(self, status: str) -> None:
        REPORTS.mkdir(parents=True, exist_ok=True)
        self.report.generated_at_utc = datetime.now(timezone.utc).isoformat()
        self.report.finished_at_utc = datetime.now(timezone.utc).isoformat()
        self.report.status = status
        self.report.stopped_compose_project = self.stopped_compose_project
        path = Path(self.args.report_path) if self.args.report_path else REPORTS / f"compose-rehearsal-{_stamp()}.json"
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self.report)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"compose rehearsal report: {path}")


def assert_safe_compose_project_name(name: str) -> None:
    if not name or not name.strip():
        raise ValueError("Compose project name cannot be empty.")
    if not SAFE_PROJECT_RE.fullmatch(name):
        raise ValueError(
            f"Refusing Compose project name {name!r}. Use a thoughtpins-* project name so teardown cannot target unrelated Compose projects."
        )


def docker_command(wsl_distro: str) -> list[str]:
    """Resolve a Docker command without silently crossing host boundaries."""
    if not wsl_distro:
        return [shutil.which("docker") or "docker"]
    if os.name != "nt":
        raise ValueError("--wsl-distro is supported only on Windows hosts.")
    if not SAFE_WSL_DISTRO_RE.fullmatch(wsl_distro):
        raise ValueError(f"Refusing unsafe WSL distribution name {wsl_distro!r}.")
    return ["wsl.exe", "-d", wsl_distro, "-u", "root", "--", "docker"]


def wait_for_health(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    body = response.read().decode("utf-8", errors="replace")
                    if '"status":"ok"' in body.replace(" ", "") or "status" in body and "ok" in body:
                        return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for {url}: {_redact(last_error)}")


def _display_command(command: list[str]) -> str:
    return " ".join(_redact(part) for part in command)


def _redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(postgresql"):
            redacted = pattern.sub(r"\1***:***@", redacted)
        elif pattern.pattern.startswith("(redis"):
            redacted = pattern.sub(r"\1***@", redacted)
        else:
            redacted = pattern.sub("***", redacted)
    return redacted


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
