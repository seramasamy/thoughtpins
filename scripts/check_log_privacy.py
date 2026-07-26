"""Fail if runtime logs expose account or external platform identifiers."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGER_METHODS = {"trace", "debug", "info", "warning", "error", "critical"}
SENSITIVE_TEMPLATE_PATTERNS = [
    re.compile(r"\bemail\s*=\s*\{\}"),
    re.compile(r"\bphone\s*=\s*\{\}"),
    re.compile(r"\btelegram\s*=\s*\{\}"),
    re.compile(r"\bchat(?:_id)?\s*=\s*\{\}"),
    re.compile(r"\bfor\s+chat\s+\{\}"),
    re.compile(r"\b(api[_-]?key|password|token)\s*=\s*\{\}"),
]
BOT_USER_ID_PATTERN = re.compile(r"\buser_id\s*=\s*\{\}")
EXCLUDED_DIRS = {"__pycache__"}


def main(root: Path = ROOT) -> int:
    findings: list[str] = []
    for path in _python_sources(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
        except SyntaxError as exc:
            findings.append(f"{rel}: could not parse Python source: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_logger_call(node):
                template = _literal_template(node)
                if not template:
                    continue
                lowered = template.lower()
                for pattern in SENSITIVE_TEMPLATE_PATTERNS:
                    if pattern.search(lowered):
                        findings.append(f"{rel}:{node.lineno}: log template exposes sensitive identifier marker")
                        break
                if "/bot/" in f"/{rel}" and BOT_USER_ID_PATTERN.search(lowered):
                    findings.append(f"{rel}:{node.lineno}: bot log template should fingerprint Telegram user IDs")
    if findings:
        print("Log privacy check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Log privacy check passed.")
    return 0


def _python_sources(root: Path):
    source_root = root / "src" / "thoughtpins"
    if not source_root.exists():
        source_root = root
    for path in source_root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def _is_logger_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in LOGGER_METHODS
        and isinstance(func.value, ast.Name)
        and func.value.id == "logger"
    )


def _literal_template(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check runtime log templates for sensitive identifier exposure.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to inspect.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(args.root.resolve()))
