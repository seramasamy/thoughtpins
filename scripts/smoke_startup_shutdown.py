"""Start a disposable Thought Pins API process and verify clean shutdown.

The smoke intentionally starts only the child process it owns, on a random local
port, with disposable SQLite/vault/vector paths. It never enumerates or kills
unrelated processes.
"""

from __future__ import annotations

import argparse
import base64
import json
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TMP_ROOT = ROOT / ".tmp" / "startup-shutdown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test isolated API startup and shutdown.")
    parser.add_argument("--timeout", type=int, default=45, help="Seconds to wait for startup.")
    parser.add_argument("--shutdown-timeout", type=int, default=20, help="Seconds to wait after the shutdown signal.")
    parser.add_argument("--json", action="store_true", help="Print a JSON report.")
    args = parser.parse_args()

    tmp_path = _make_run_dir()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = _child_env(tmp_path, port)
    command = [sys.executable, "-m", "thoughtpins.server", "--api-only"]
    started = time.perf_counter()
    process = _start_child(command, env)
    report: dict[str, Any] = {
        "app": "Thought Pins",
        "command": _display_command(command),
        "child_pid": process.pid,
        "base_url": base_url,
        "process_scope": "only the child_pid started by this script is signaled",
        "temp_root": str(tmp_path),
        "started": False,
        "health": None,
        "client_config": None,
        "app_route": None,
        "shutdown": None,
        "port_closed_after_shutdown": False,
        "stdout_tail": "",
        "stderr_tail": "",
    }
    ok = False
    try:
        health = _wait_json(f"{base_url}/health", timeout=args.timeout)
        config = _request_json(f"{base_url}/v1/client-config", timeout=5)
        app_route = _request_text(f"{base_url}/app", timeout=5)
        report.update(
            {
                "started": True,
                "health": _select_keys(
                    health, ["status", "version", "environment", "auth_required", "maintenance_mode"]
                ),
                "client_config": _select_keys(
                    config,
                    [
                        "app_name",
                        "api_version",
                        "environment",
                        "auth_required",
                    ],
                ),
                "app_route": {
                    "status": "ok" if "Thought Pins" in app_route else "unexpected_content",
                    "contains_brand": "Thought Pins" in app_route,
                },
            }
        )
        shutdown = _shutdown_child(process, timeout=args.shutdown_timeout)
        report["shutdown"] = shutdown
        report["port_closed_after_shutdown"] = _wait_port_closed("127.0.0.1", port, timeout=8)
        ok = (
            report["health"].get("status") == "ok"
            and report["client_config"].get("app_name") == "Thought Pins"
            and report["app_route"].get("contains_brand") is True
            and shutdown.get("exited") is True
            and shutdown.get("forced_kill") is False
            and report["port_closed_after_shutdown"] is True
        )
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        if process.poll() is None:
            report["cleanup"] = _force_stop_child(process)
        stdout_tail, stderr_tail = _collect_output(process)
        report["stdout_tail"] = stdout_tail
        report["stderr_tail"] = stderr_tail
        report["seconds"] = round(time.perf_counter() - started, 2)
        report["temp_cleanup"] = _cleanup_run_dir(tmp_path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report, ok)
    return 0 if ok else 1


def _make_run_dir() -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"run-{uuid.uuid4().hex[:12]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _cleanup_run_dir(path: Path) -> dict[str, Any]:
    try:
        shutil.rmtree(path)
        return {"removed": True, "path": str(path)}
    except Exception as exc:
        return {"removed": False, "path": str(path), "error": str(exc)}


def _child_env(tmp_path: Path, port: int) -> dict[str, str]:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    reports_dir = tmp_path / "reports"
    backups_dir = tmp_path / "backups"
    qdrant_dir = tmp_path / "qdrant"
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
            "TELEGRAM_TEST_MODE": "false",
            "ENABLE_FOUNDER_MODE": "false",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_ALLOWED_USER_IDS": "",
            "LLM_PROVIDER": "openai_compatible",
            "LLM_API_KEY": "",
            "LLM_BASE_URL": "https://api.invalid.local/v1",
            "LLM_MODEL": "startup-smoke-model",
            "LLM_HEALTHCHECK_LIVE": "false",
            "VECTOR_HEALTHCHECK_LIVE": "false",
            "EMBEDDING_PROVIDER": "local",
            "OPENAI_API_KEY": "",
            "JINA_API_KEY": "",
            "FIRECRAWL_API_KEY": "",
            "APIFY_API_TOKEN": "",
            "SENTRY_DSN": "",
            "REDIS_URL": "",
            "JSON_LOGS": "true",
            "LOG_LEVEL": "WARNING",
            "VAULT_PATH": str(vault_dir),
            "REPORTS_PATH": str(reports_dir),
            "BACKUPS_PATH": str(backups_dir),
            "QDRANT_PATH": str(qdrant_dir),
            "DATA_ENCRYPTION_KEY": fernet_key,
            "SECURITY_HEADERS_ENABLED": "true",
            "MAINTENANCE_MODE": "false",
        }
    )
    return env


def _start_child(command: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )


def _shutdown_child(process: subprocess.Popen[str], *, timeout: int) -> dict[str, Any]:
    if process.poll() is not None:
        return {"signal": "none", "exited": True, "returncode": process.returncode, "forced_kill": False}
    signal_name = "SIGTERM"
    try:
        # sys.platform rather than os.name: static checkers treat this exact
        # form as a platform guard and skip the branch entirely when analysing
        # for another platform, where signal.CTRL_BREAK_EVENT does not exist.
        if sys.platform == "win32":
            signal_name = "CTRL_BREAK_EVENT"
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    except Exception as exc:
        signal_name = f"fallback_terminate_after_{type(exc).__name__}"
        process.terminate()
    try:
        returncode = process.wait(timeout=timeout)
        return {"signal": signal_name, "exited": True, "returncode": returncode, "forced_kill": False}
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = process.wait(timeout=10)
        return {"signal": signal_name, "exited": True, "returncode": returncode, "forced_kill": True}


def _force_stop_child(process: subprocess.Popen[str]) -> dict[str, Any]:
    process.terminate()
    try:
        returncode = process.wait(timeout=8)
        return {"returncode": returncode, "forced_kill": False}
    except subprocess.TimeoutExpired:
        process.kill()
        return {"returncode": process.wait(timeout=8), "forced_kill": True}


def _wait_json(url: str, *, timeout: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            return _request_json(url, timeout=3)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {url}: {last_error}")


def _request_json(url: str, *, timeout: int) -> dict[str, Any]:
    text = _request_text(url, timeout=timeout)
    return json.loads(text)


def _request_text(url: str, *, timeout: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ThoughtPinsStartupSmoke/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _wait_port_closed(host: str, port: int, *, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex((host, port)) != 0:
                return True
        time.sleep(0.25)
    return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _collect_output(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        stdout, stderr = "", ""
    return _tail(stdout), _tail(stderr)


def _tail(value: str, *, lines: int = 30) -> str:
    return "\n".join((value or "").splitlines()[-lines:])


def _select_keys(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys}


def _display_command(command: list[str]) -> list[str]:
    return [Path(command[0]).name if index == 0 else part for index, part in enumerate(command)]


def _print_report(report: dict[str, Any], ok: bool) -> None:
    print(f"startup: {'ok' if report.get('started') else 'failed'}")
    print(f"health: {report.get('health')}")
    print(f"client_config: {report.get('client_config')}")
    print(f"app_route: {report.get('app_route')}")
    print(f"shutdown: {report.get('shutdown')}")
    print(f"port_closed_after_shutdown: {report.get('port_closed_after_shutdown')}")
    if report.get("error"):
        print(f"error: {report['error']}")
    if report.get("stderr_tail"):
        print("stderr tail:")
        print(report["stderr_tail"])
    print("startup/shutdown smoke passed" if ok else "startup/shutdown smoke failed")


if __name__ == "__main__":
    raise SystemExit(main())
