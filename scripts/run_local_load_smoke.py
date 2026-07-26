"""Run bounded k6 probes against a disposable local Thought Pins API.

The harness owns exactly one child process, uses a random loopback port and
isolated storage, and removes that storage after graceful shutdown. It is a
developer/reviewer proof; production capacity decisions still require the same
scripts against the deployed PostgreSQL and Redis topology.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import smoke_startup_shutdown as runtime

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "load" / "local-k6-latest.json"
DEFAULT_K6_CANDIDATES = (ROOT / ".deps" / "k6-v2.0.0" / "bin" / "k6-v2.0.0-windows-amd64" / "k6.exe",)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k6", type=Path, help="Path to the k6 executable.")
    parser.add_argument("--health-vus", type=int, default=100)
    parser.add_argument("--health-duration", default="15s")
    parser.add_argument("--flow-vus", type=int, default=5)
    parser.add_argument("--flow-duration", default="10s")
    parser.add_argument("--skip-flow", action="store_true")
    args = parser.parse_args()

    k6 = _resolve_k6(args.k6)
    temp_root = runtime._make_run_dir()
    port = runtime._free_port()
    base_url = f"http://127.0.0.1:{port}"
    child_env = runtime._child_env(temp_root, port)
    password = f"Load-{secrets.token_urlsafe(18)}-9a"
    child_env.update(
        {
            "REQUIRE_API_AUTH": "true",
            "JWT_SECRET": secrets.token_urlsafe(48),
            "EMAIL_VERIFICATION_REQUIRED": "false",
            "RATE_LIMIT_ENABLED": "false",
            "PROCESS_ENTRIES_ASYNC": "true",
            "INGESTION_QUEUE_BACKEND": "thread",
            "INGESTION_WORKER_THREADS": "2",
            "INGESTION_MAX_RETRIES": "1",
            "LOG_LEVEL": "ERROR",
        }
    )
    command = [sys.executable, "-m", "thoughtpins.server", "--api-only"]
    process = runtime._start_child(command, child_env)
    started = time.perf_counter()
    probes: list[dict[str, Any]] = []
    shutdown: dict[str, Any] = {}
    error: str | None = None

    try:
        health = runtime._wait_json(f"{base_url}/health", timeout=45)
        if health.get("status") != "ok":
            raise RuntimeError(f"disposable API returned unhealthy startup status: {health.get('status')}")
        probes.append(
            _run_k6(
                k6,
                ROOT / "load" / "k6-health.js",
                base_url=base_url,
                extra_env={
                    "VUS": str(_positive(args.health_vus, "health-vus")),
                    "DURATION": args.health_duration,
                    "P95_MS": "500",
                },
                timeout=_duration_timeout(args.health_duration),
            )
        )
        if not args.skip_flow:
            probes.append(
                _run_k6(
                    k6,
                    ROOT / "load" / "k6-api-flow.js",
                    base_url=base_url,
                    extra_env={
                        "VUS": str(_positive(args.flow_vus, "flow-vus")),
                        "DURATION": args.flow_duration,
                        "P95_MS": "1000",
                        "EMAIL": f"load-{secrets.token_hex(8)}@example.com",
                        "PASSWORD": password,
                        "REGISTER": "true",
                        "REQUEST_TIMEOUT": "10s",
                        "GRACEFUL_STOP": "10s",
                    },
                    timeout=_duration_timeout(args.flow_duration),
                )
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        shutdown = runtime._shutdown_child(process, timeout=20)
        port_closed = runtime._wait_port_closed("127.0.0.1", port, timeout=8)
        if process.poll() is None:
            runtime._force_stop_child(process)
        stdout_tail, stderr_tail = runtime._collect_output(process)
        cleanup = runtime._cleanup_run_dir(temp_root)

    report = {
        "schema_version": 1,
        "tool": _k6_version(k6),
        "topology": "disposable_loopback_sqlite",
        "production_capacity_proof": False,
        "probes": probes,
        "shutdown": shutdown,
        "port_closed_after_shutdown": port_closed,
        "temporary_storage_removed": cleanup.get("removed") is True,
        "seconds": round(time.perf_counter() - started, 3),
        "error": error,
        "server_stdout_tail": _redact_tail(stdout_tail),
        "server_stderr_tail": _redact_tail(stderr_tail),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = (
        error is None
        and bool(probes)
        and all(probe["passed"] for probe in probes)
        and shutdown.get("exited") is True
        and shutdown.get("forced_kill") is False
        and port_closed
        and cleanup.get("removed") is True
    )
    print(json.dumps({key: value for key, value in report.items() if not key.startswith("server_")}, indent=2))
    print(f"Local load smoke {'passed' if ok else 'failed'}; report: {REPORT_PATH}")
    return 0 if ok else 1


def _run_k6(
    executable: Path,
    script: Path,
    *,
    base_url: str,
    extra_env: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(extra_env)
    env["BASE_URL"] = base_url
    started = time.perf_counter()
    completed = subprocess.run(
        [str(executable), "run", "--quiet", str(script)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    result = {
        "name": script.stem,
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "seconds": round(time.perf_counter() - started, 3),
        "output_tail": _redact_tail("\n".join((completed.stdout, completed.stderr))),
    }
    if completed.returncode != 0:
        raise RuntimeError(f"{script.name} failed:\n{result['output_tail']}")
    return result


def _resolve_k6(requested: Path | None) -> Path:
    candidates = ([requested] if requested else []) + list(DEFAULT_K6_CANDIDATES)
    path_from_shell = shutil.which("k6")
    if path_from_shell:
        candidates.append(Path(path_from_shell))
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("k6 was not found; pass --k6 or install the pinned reviewer tool under .deps")


def _k6_version(executable: Path) -> str:
    completed = subprocess.run(
        [str(executable), "version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return (completed.stdout or completed.stderr).strip().splitlines()[0][:120]


def _positive(value: int, name: str) -> int:
    if value < 1 or value > 500:
        raise ValueError(f"{name} must be between 1 and 500")
    return value


def _duration_timeout(value: str) -> int:
    suffix = value[-1:].lower()
    amount = float(value[:-1]) if suffix in {"s", "m"} else float(value)
    seconds = amount * 60 if suffix == "m" else amount
    if seconds <= 0 or seconds > 600:
        raise ValueError("load duration must be greater than zero and at most 10 minutes")
    return int(seconds + 90)


def _redact_tail(value: str, lines: int = 45) -> str:
    text = "\n".join((value or "").splitlines()[-lines:]).replace("\\", "/")
    root = str(ROOT).replace("\\", "/")
    home = str(Path.home()).replace("\\", "/")
    for private_path, replacement in ((root, "<repo>"), (home, "<home>")):
        text = text.replace(private_path, replacement)
        text = text.replace(private_path.replace("/", "//"), replacement)
    return text


if __name__ == "__main__":
    raise SystemExit(main())
