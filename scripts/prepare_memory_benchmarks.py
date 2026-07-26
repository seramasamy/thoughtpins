"""Fetch or verify pinned external memory benchmarks in ignored scratch storage."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.memory.benchmark_datasets import (  # noqa: E402
    DatasetSpec,
    load_dataset_specs,
    verify_dataset_file,
)

MANIFEST = ROOT / "deploy" / "quality" / "memory-benchmarks.json"
DEFAULT_DESTINATION = ROOT / ".tmp" / "benchmark-corpora"
_ALLOWED_DOWNLOAD_HOSTS = frozenset({"huggingface.co", "cdn-lfs.huggingface.co"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--include-diagnostic", action="store_true", help="Also prepare noncommercial diagnostic data.")
    args = parser.parse_args()

    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    ok = True
    for spec in load_dataset_specs(MANIFEST):
        if spec.kind == "excluded":
            print(f"excluded {spec.id}: {spec.exclusion_reason}")
            continue
        if spec.allowed_uses == ("diagnostic_only",) and not args.include_diagnostic:
            print(f"skipped {spec.id}: diagnostic-only corpus")
            continue
        target = destination / spec.local_path
        try:
            if spec.kind == "https_file":
                _prepare_file(spec, target, verify_only=args.verify_only)
            elif spec.kind == "git":
                _prepare_git(spec, target, verify_only=args.verify_only)
            else:
                raise ValueError(f"unsupported dataset kind: {spec.kind}")
            print(f"verified {spec.id}: {target}")
        except (OSError, RuntimeError, ValueError, httpx.HTTPError, subprocess.SubprocessError) as exc:
            ok = False
            print(f"failed {spec.id}: {exc}")
    return 0 if ok else 1


def _prepare_file(spec: DatasetSpec, target: Path, *, verify_only: bool) -> None:
    problems = verify_dataset_file(target, spec)
    if problems and not verify_only:
        _download_file(spec, target)
        problems = verify_dataset_file(target, spec)
    if problems:
        raise RuntimeError("; ".join(problems))


def _download_file(spec: DatasetSpec, target: Path) -> None:
    source_host = (urlparse(spec.source).hostname or "").lower()
    if source_host not in _ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"download host is not allowlisted: {source_host}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.download")
    observed = 0
    try:
        with httpx.stream("GET", spec.source, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in response.iter_bytes(1024 * 1024):
                    observed += len(chunk)
                    if observed > spec.bytes:
                        raise RuntimeError(f"download exceeded pinned size of {spec.bytes} bytes")
                    stream.write(chunk)
        if observed != spec.bytes:
            raise RuntimeError(f"download size mismatch: expected {spec.bytes}, found {observed}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare_git(spec: DatasetSpec, target: Path, *, verify_only: bool) -> None:
    if not (target / ".git").is_dir():
        if verify_only:
            raise RuntimeError("repository is missing")
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--no-checkout", spec.source, str(target)],
            check=True,
            cwd=target.parent,
            timeout=300,
        )
        subprocess.run(["git", "checkout", "--detach", spec.revision], check=True, cwd=target, timeout=300)
    observed = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            cwd=target,
            capture_output=True,
            text=True,
            timeout=30,
        )
        .stdout.strip()
        .lower()
    )
    if observed != spec.revision:
        raise RuntimeError(f"revision mismatch: expected {spec.revision}, found {observed}")


if __name__ == "__main__":
    raise SystemExit(main())
