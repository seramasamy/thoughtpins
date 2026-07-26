"""Reject new Python encoding, dead-code, and complexity debt."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from radon.complexity import cc_visit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "deploy" / "quality" / "python-maintainability.json"
UTF8_BOM = b"\xef\xbb\xbf"


def main() -> int:
    try:
        config = _load_config(CONFIG)
        files = _python_files(config)
        findings = _encoding_findings(files)
        findings.extend(_complexity_findings(files, config))
        findings.extend(_vulture_findings(config))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"Python maintainability check could not run: {exc}")
        return 2
    if findings:
        print("Python maintainability check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Python maintainability check passed: UTF-8, complexity ratchets, and high-confidence dead code are clean.")
    return 0


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("python maintainability schema_version must be 1")
    return payload


def _python_files(config: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    for source_root in config["source_roots"]:
        root = ROOT / str(source_root)
        if not root.is_dir():
            raise ValueError(f"configured Python source root is missing: {source_root}")
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(set(files))


def _encoding_findings(files: list[Path]) -> list[str]:
    return [
        f"ENC001 {path.relative_to(ROOT).as_posix()}: UTF-8 BOM is forbidden"
        for path in files
        if path.read_bytes().startswith(UTF8_BOM)
    ]


def _complexity_findings(files: list[Path], config: dict[str, Any]) -> list[str]:
    default_limit = int(config["default_max_cyclomatic_complexity"])
    legacy = {str(key): int(value) for key, value in config.get("legacy_complexity_budgets", {}).items()}
    observed: dict[str, int] = {}
    findings: list[str] = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        for block in cc_visit(path.read_text(encoding="utf-8")):
            if block.__class__.__name__ == "Class":
                continue
            class_name = str(getattr(block, "classname", "") or "")
            qualified_name = f"{class_name}.{block.name}" if class_name else block.name
            key = f"{relative}::{qualified_name}"
            complexity = int(block.complexity)
            observed[key] = max(complexity, observed.get(key, 0))
            limit = legacy.get(key, default_limit)
            if complexity > limit:
                findings.append(f"CC001 {key}: complexity {complexity} exceeds ratchet {limit}")
    for key in sorted(set(legacy) - set(observed)):
        findings.append(f"CC002 {key}: stale legacy complexity budget")
    return findings


def _vulture_findings(config: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "vulture",
        *[str(ROOT / source_root) for source_root in config["source_roots"]],
        "--min-confidence",
        str(int(config["vulture_min_confidence"])),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    if completed.returncode not in {0, 1}:
        raise subprocess.SubprocessError(completed.stderr.strip() or "vulture failed")
    return [f"DEAD001 {line}" for line in completed.stdout.splitlines() if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
