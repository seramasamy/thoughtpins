"""Run closed-beta evidence against a disposable local API runtime.

This starts only the API child process owned by this script, points it at scratch
SQLite/vault/vector/backup directories, runs the existing evidence collector, and
then shuts the child down. It is the safest local substitute for a staging smoke
until Docker/PostgreSQL and Playwright can run on an unrestricted host.
"""

from __future__ import annotations

import argparse
import base64
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TMP_ROOT = ROOT / ".tmp" / "local-evidence"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run disposable local closed-beta evidence.")
    parser.add_argument("--full-tests", action="store_true", help="Run full pytest inside the evidence collector.")
    parser.add_argument(
        "--telegram-api", action="store_true", help="Also validate the configured Telegram bot through Telegram API."
    )
    parser.add_argument("--live-article", action="store_true", help="Exercise live public article provider checks.")
    parser.add_argument("--web-smoke", action="store_true", help="Attempt Playwright browser smoke/screenshots.")
    parser.add_argument("--compose-rehearsal-report", default="", help="Pass-through Compose rehearsal JSON proof.")
    parser.add_argument("--playwright-report", default="", help="Pass-through Playwright JSON proof.")
    parser.add_argument(
        "--web-smoke-dir", default="reports/web-smoke", help="Pass-through Playwright screenshot directory."
    )
    parser.add_argument(
        "--use-latest-external-proof", action="store_true", help="Pass-through latest reports/* proof validation."
    )
    parser.add_argument("--keep-temp", action="store_true", help="Keep scratch runtime files after the run.")
    parser.add_argument("--port", type=int, default=0, help="Specific local port; defaults to a random free port.")
    parser.add_argument(
        "--strict-complete",
        action="store_true",
        help="Pass through strict evidence completeness; exits nonzero when Docker/Playwright/external proof is incomplete.",
    )
    args = parser.parse_args()

    run_dir = _make_run_dir()
    port = args.port or _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_env = _child_env(run_dir, port)
    collector_env = _collector_env(server_env)
    process = _start_api(server_env)
    returncode = 1
    try:
        _wait_for_health(base_url, timeout=60)
        print(f"local api: {base_url}")
        command = [
            sys.executable,
            "scripts/collect_closed_beta_evidence.py",
            "--api-base-url",
            base_url,
        ]
        if args.full_tests:
            command.append("--full-tests")
        if args.telegram_api:
            command.append("--telegram-api")
        if args.live_article:
            command.append("--live-article")
        if args.web_smoke:
            command.append("--web-smoke")
        if args.compose_rehearsal_report:
            command.extend(["--compose-rehearsal-report", args.compose_rehearsal_report])
        if args.playwright_report:
            command.extend(["--playwright-report", args.playwright_report])
        if args.web_smoke_dir:
            command.extend(["--web-smoke-dir", args.web_smoke_dir])
        if args.use_latest_external_proof:
            command.append("--use-latest-external-proof")
        if args.strict_complete:
            command.append("--strict-complete")
        completed = subprocess.run(command, cwd=ROOT, env=collector_env, text=True)
        returncode = completed.returncode
    finally:
        shutdown = _shutdown_child(process, timeout=20)
        print(f"local api shutdown: {shutdown}")
        if not args.keep_temp:
            _cleanup_run_dir(run_dir)
        else:
            print(f"kept temp: {run_dir}")
    return returncode


def _make_run_dir() -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"run-{uuid.uuid4().hex[:12]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _child_env(run_dir: Path, port: int) -> dict[str, str]:
    data_dir = run_dir / "data"
    vault_dir = run_dir / "vault"
    reports_dir = run_dir / "runtime-reports"
    backups_dir = run_dir / "backups"
    qdrant_dir = run_dir / "qdrant"
    for path in (data_dir, vault_dir, reports_dir, backups_dir, qdrant_dir):
        path.mkdir(parents=True, exist_ok=True)

    fernet_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SRC),
            "PYTHONUNBUFFERED": "1",
            "ENVIRONMENT": "development",
            "APP_NAME": "Thought Pins",
            "API_HOST": "127.0.0.1",
            "API_PORT": str(port),
            "DATABASE_URL": f"sqlite:///{(data_dir / 'thoughtpins.sqlite3').as_posix()}",
            "AUTO_CREATE_TABLES": "true",
            "RUN_STARTUP_RECOVERY": "false",
            "REQUIRE_API_AUTH": "false",
            "SYSTEM_LOCKED": "false",
            "ALLOW_USER_API_KEYS": "false",
            "RETURN_API_KEY_ON_REGISTER": "false",
            "RATE_LIMIT_ENABLED": "false",
            "PROCESS_ENTRIES_ASYNC": "false",
            "INGESTION_QUEUE_BACKEND": "thread",
            "ENABLE_TELEGRAM_BOT": "false",
            "TELEGRAM_TEST_MODE": "true",
            "ENABLE_FOUNDER_MODE": "true",
            "CONFIDENTIAL_ACCESS_CODE": "local-smoke-only",
            "FOUNDER_ACCESS_CODE": "local-smoke-only",
            "LLM_HEALTHCHECK_LIVE": "false",
            "VECTOR_HEALTHCHECK_LIVE": "false",
            "VECTOR_MODE": "qdrant_local",
            "EMBEDDING_PROVIDER": "openai",
            "VAULT_PATH": str(vault_dir),
            "REPORTS_PATH": str(reports_dir),
            "BACKUPS_PATH": str(backups_dir),
            "QDRANT_PATH": str(qdrant_dir),
            "DATA_ENCRYPTION_KEY": fernet_key,
            "LOG_LEVEL": "WARNING",
            "JSON_LOGS": "true",
            "MAINTENANCE_MODE": "false",
            "THOUGHTPINS_RUNTIME_SMOKE_HTTP_TIMEOUT_SECONDS": "180",
        }
    )
    return env


def _collector_env(server_env: dict[str, str]) -> dict[str, str]:
    env = server_env.copy()
    # Let Telegram startup validation derive ENABLE_TELEGRAM_BOT from the real
    # token/.env when --telegram-api is requested; the API child remains disabled.
    env.pop("ENABLE_TELEGRAM_BOT", None)
    env["ENABLE_FOUNDER_MODE"] = "false"
    return env


def _start_api(env: dict[str, str]) -> subprocess.Popen[str]:
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        [sys.executable, "-m", "thoughtpins.server", "--api-only"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )


def _wait_for_health(base_url: str, *, timeout: int) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {base_url}/health: {last_error}")


def _shutdown_child(process: subprocess.Popen[str], *, timeout: int) -> dict[str, object]:
    if process.poll() is not None:
        return {"exited": True, "returncode": process.returncode, "forced_kill": False}
    signal_name = "SIGTERM"
    try:
        if os.name == "nt":
            signal_name = "CTRL_BREAK_EVENT"
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    except Exception:
        process.terminate()
        signal_name = "terminate"
    try:
        returncode = process.wait(timeout=timeout)
        return {"signal": signal_name, "exited": True, "returncode": returncode, "forced_kill": False}
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = process.wait(timeout=10)
        return {"signal": signal_name, "exited": True, "returncode": returncode, "forced_kill": True}


def _cleanup_run_dir(path: Path) -> None:
    root = ROOT.resolve()
    target = path.resolve()
    target.relative_to(root)
    shutil.rmtree(target)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    raise SystemExit(main())
