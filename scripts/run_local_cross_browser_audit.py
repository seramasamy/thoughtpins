"""Audit the backend-served site and app in three browser engines.

Only the disposable API child created here is signaled. The audit uses an empty
SQLite database and random loopback port, so it never captures personal data or
depends on an already-running developer service.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import smoke_startup_shutdown as runtime

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.timeout < 60 or args.timeout > 1800:
        raise ValueError("timeout must be between 60 and 1800 seconds")

    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required for the cross-browser audit")
    run_dir = runtime._make_run_dir()
    port = runtime._free_port()
    base_url = f"http://127.0.0.1:{port}"
    child_env = runtime._child_env(run_dir, port)
    child_env["LOG_LEVEL"] = "ERROR"
    process = runtime._start_child([sys.executable, "-m", "thoughtpins.server", "--api-only"], child_env)
    audit_returncode = 1
    shutdown: dict[str, object] = {}
    port_closed = False
    cleanup_removed = False
    try:
        health = runtime._wait_json(f"{base_url}/health", timeout=45)
        if health.get("status") != "ok":
            raise RuntimeError("disposable API did not become healthy")
        env = os.environ.copy()
        env["THOUGHTPINS_LIVE_URL"] = base_url
        completed = subprocess.run(
            [npm, "run", "smoke:cross-browser"],
            cwd=FRONTEND,
            env=env,
            check=False,
            timeout=args.timeout,
        )
        audit_returncode = completed.returncode
    finally:
        shutdown = runtime._shutdown_child(process, timeout=30)
        port_closed = runtime._wait_port_closed("127.0.0.1", port, timeout=8)
        if process.poll() is None:
            runtime._force_stop_child(process)
        runtime._collect_output(process)
        cleanup_removed = runtime._cleanup_run_dir(run_dir).get("removed") is True

    ok = (
        audit_returncode == 0
        and shutdown.get("exited") is True
        and shutdown.get("forced_kill") is False
        and port_closed
        and cleanup_removed
    )
    print(f"browser audit return code: {audit_returncode}")
    print(f"disposable API shutdown: {shutdown}")
    print(f"port released: {port_closed}; temporary storage removed: {cleanup_removed}")
    print(f"Cross-browser audit {'passed' if ok else 'failed'}; evidence: reports/cross-browser")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
