"""One-command local engineering verification.

Default mode is offline-safe. Add `--live-llm` for real configured-LLM workflow tests
and `--api-base-url` for checks against a running local/staging API.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Step:
    name: str
    command: list[str]
    timeout: int


@dataclass
class Result:
    name: str
    status: str
    seconds: float


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Thought Pins engineering checks.")
    parser.add_argument("--live-llm", action="store_true", help="Run live configured-LLM synthetic workflow tests.")
    parser.add_argument("--live-article", action="store_true", help="Run live article provider and ingest smoke tests.")
    parser.add_argument(
        "--telegram-api", action="store_true", help="Validate configured Telegram bot token via Telegram API."
    )
    parser.add_argument("--api-base-url", default="", help="Running API base URL for founder/parity smoke.")
    parser.add_argument("--skip-release", action="store_true", help="Skip the full release gate.")
    args = parser.parse_args()

    py = _project_python()
    steps: list[Step] = []
    if not args.skip_release:
        release = [py, "scripts/release_check.py"]
        if args.api_base_url:
            release.extend(["--api-base-url", args.api_base_url.rstrip("/")])
        steps.append(Step("release gate", release, 360))
    steps.append(Step("runtime log privacy", [py, "scripts/check_log_privacy.py"], 30))
    steps.append(Step("public export hygiene", [py, "scripts/check_public_export.py"], 60))
    steps.append(Step("workspace package hygiene", [py, "scripts/check_workspace_hygiene.py"], 30))

    parity = [py, "scripts/production_parity_check.py"]
    if args.api_base_url:
        parity.extend(["--base-url", args.api_base_url.rstrip("/")])
    steps.append(Step("production parity shape", parity, 90))

    if args.api_base_url:
        env = os.environ.copy()
        env["THOUGHTPINS_BASE_URL"] = args.api_base_url.rstrip("/")
        steps.append(Step("founder runtime smoke", [py, "scripts/smoke_founder_local.py"], 60))
    if args.live_llm:
        steps.extend(
            [
                Step("live LLM workflow", [py, "scripts/evaluate_llm_workflow.py"], 240),
                Step("live LLM behavior matrix", [py, "scripts/evaluate_llm_behavior_matrix.py"], 360),
            ]
        )
    if args.live_article:
        steps.extend(
            [
                Step(
                    "article provider public smoke",
                    [
                        py,
                        "scripts/smoke_article_fetch_providers.py",
                        "--url",
                        "https://www.paulgraham.com/greatwork.html",
                    ],
                    90,
                ),
                Step(
                    "article provider restricted smoke",
                    [
                        py,
                        "scripts/smoke_article_fetch_providers.py",
                        "--chain-only",
                        "--expect-needs-text",
                        "--url",
                        "https://www.wsj.com/articles/long-running-ai-agents-are-here-3e3aa89b",
                    ],
                    60,
                ),
                Step("live article ingest smoke", [py, "scripts/smoke_live_article_ingest.py"], 180),
            ]
        )
    if args.telegram_api:
        steps.append(Step("telegram API smoke", [py, "scripts/smoke_telegram_api.py"], 60))

    results: list[Result] = []
    ok = True
    for step in steps:
        started = time.perf_counter()
        print(f"\n==> {step.name}")
        try:
            env = _step_env(args.api_base_url) if step.name == "founder runtime smoke" else _step_env("")
            completed = subprocess.run(step.command, cwd=ROOT, env=env, timeout=step.timeout)
            status = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            status = "timeout"
        seconds = time.perf_counter() - started
        results.append(Result(step.name, status, seconds))
        ok &= status == "passed"

    print("\nEngineering check summary:")
    for result in results:
        print(f"- {result.status:7} {result.seconds:6.1f}s  {result.name}")
    return 0 if ok else 1


def _step_env(api_base_url: str) -> dict[str, str]:
    env = os.environ.copy()
    if api_base_url:
        env["THOUGHTPINS_BASE_URL"] = api_base_url.rstrip("/")
    src = str(ROOT / "src")
    current = env.get("PYTHONPATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if src not in parts:
        parts.insert(0, src)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _project_python(root: Path = ROOT) -> str:
    """Use the repository environment when the runner is started globally."""
    configured = os.environ.get("THOUGHTPINS_PYTHON", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_file():
            raise SystemExit(f"THOUGHTPINS_PYTHON does not exist: {candidate}")
        return str(candidate.resolve())

    candidates = (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return sys.executable


if __name__ == "__main__":
    raise SystemExit(main())
