"""Enforce size ratchets and dependency direction for product source code."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "deploy" / "quality" / "architecture-budget.json"


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str

    def render(self) -> str:
        return f"{self.code} {self.path}: {self.message}"


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("architecture budget schema_version must be 1")
    return payload


def evaluate(root: Path, config: dict[str, Any]) -> list[Finding]:
    findings = _line_budget_findings(root, config)
    findings.extend(_dependency_findings(root, config))
    return sorted(findings, key=lambda finding: (finding.path, finding.code, finding.message))


def _line_budget_findings(root: Path, config: dict[str, Any]) -> list[Finding]:
    defaults = {str(key): int(value) for key, value in config["default_line_limits"].items()}
    legacy = {str(key): int(value) for key, value in config.get("legacy_line_budgets", {}).items()}
    findings: list[Finding] = []
    seen: set[str] = set()

    for source_root in config["source_roots"]:
        base = root / source_root
        if not base.exists():
            findings.append(Finding("ARCH001", source_root, "configured source root is missing"))
            continue
        for path in sorted(candidate_source_files(base, defaults)):
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            default_limit = defaults[path.suffix.lower()]
            limit = legacy.get(relative, default_limit)
            if line_count > limit:
                kind = "legacy ratchet" if relative in legacy else "default budget"
                findings.append(
                    Finding(
                        "ARCH002",
                        relative,
                        f"{line_count} lines exceeds {kind} of {limit}; extract behavior before adding more",
                    )
                )

    for relative in sorted(set(legacy) - seen):
        findings.append(Finding("ARCH003", relative, "legacy budget points to a missing or unsupported source file"))
    return findings


def candidate_source_files(base: Path, defaults: dict[str, int]):
    excluded_parts = {"build", "dist", "node_modules", ".gradle", "Pods", "__pycache__"}
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in defaults:
            continue
        if any(part in excluded_parts for part in path.parts):
            continue
        yield path


def _dependency_findings(root: Path, config: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for rule in config.get("dependency_rules", []):
        prefixes = tuple(str(prefix) for prefix in rule["forbidden_import_prefixes"])
        exceptions = {
            (str(item["path"]), str(item["import"])): str(item.get("reason") or "")
            for item in rule.get("exceptions", [])
        }
        used_exceptions: set[tuple[str, str]] = set()
        for source_path in rule["paths"]:
            base = root / source_path
            if not base.exists():
                findings.append(Finding("ARCH004", source_path, f"dependency rule '{rule['name']}' path is missing"))
                continue
            for path in sorted(base.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                relative = path.relative_to(root).as_posix()
                for imported in python_imports(path):
                    if not imported.startswith(prefixes):
                        continue
                    matched = next(
                        (
                            key
                            for key in exceptions
                            if key[0] == relative and (imported == key[1] or imported.startswith(f"{key[1]}."))
                        ),
                        None,
                    )
                    if matched:
                        used_exceptions.add(matched)
                        continue
                    findings.append(
                        Finding(
                            "ARCH005",
                            relative,
                            f"dependency rule '{rule['name']}' forbids import {imported}",
                        )
                    )
        for key, reason in sorted(exceptions.items()):
            if key not in used_exceptions:
                findings.append(
                    Finding(
                        "ARCH006",
                        key[0],
                        f"stale dependency exception for {key[1]} ({reason or 'no reason supplied'})",
                    )
                )
    return findings


def python_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    try:
        findings = evaluate(root, load_config(config_path))
    except (OSError, ValueError, json.JSONDecodeError, SyntaxError) as exc:
        print(f"Architecture budget check failed to run: {exc}")
        return 2

    if findings:
        print("Architecture budget check failed:")
        for finding in findings:
            print(f"- {finding.render()}")
        return 1
    print("Architecture budget check passed: file-size ratchets and dependency direction are intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
