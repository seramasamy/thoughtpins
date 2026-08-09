"""Audit the dependencies that the production lock does not contain.

`requirements-prod.lock` is exported with `--no-dev --extra workers`, so it holds
78 of the project's 205 resolved packages. The release gate audits that file,
which means every optional extra — telegram, voice, reports, embeddings, graph —
was unaudited. That is not a theoretical gap: pypdf 6.14.2 sat in the `telegram`
extra with a published advisory, is imported at runtime by media extraction, and
the gate reported no known vulnerabilities the whole time. GitHub's Dependabot
found it because it reads `uv.lock`, which covers everything.

Self-hosting instructions tell people to install these extras, so a
vulnerability here reaches real deployments. This audits the full resolved
graph rather than the shipped subset.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / ".tmp" / "all-extras.lock"
CACHE_DIR = ROOT / ".tmp" / "pip-audit-cache"


def main() -> int:
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    exported = subprocess.run(
        [
            sys.executable,
            "-m",
            "uv",
            "export",
            "--frozen",
            "--all-extras",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(EXPORT_PATH),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if exported.returncode != 0:
        print("Optional extra dependency audit failed: could not export the full graph")
        if exported.stderr:
            print(exported.stderr.strip()[:500])
        return 1

    audited = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(EXPORT_PATH),
            "--require-hashes",
            "--disable-pip",
            "--vulnerability-service",
            "osv",
            "--cache-dir",
            str(CACHE_DIR),
            "--progress-spinner",
            "off",
            "--timeout",
            "30",
        ],
        cwd=ROOT,
        check=False,
    )
    if audited.returncode != 0:
        print("Optional extra dependency audit failed: fix or pin the reported packages")
        return 1

    packages = sum(1 for line in EXPORT_PATH.read_text(encoding="utf-8").splitlines() if line[:1].isalnum())
    print(f"Optional extra dependency audit passed: {packages} resolved packages, all extras included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
