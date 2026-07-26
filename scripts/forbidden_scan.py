"""Fail CI if forbidden private references or obvious secret patterns are committed."""

from __future__ import annotations

import argparse
import re
import sys
from os import walk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".deps",
    ".gradle",
    ".gradle-local",
    ".kotlin",
    ".android-local",
    ".tmp",
    ".ms-playwright",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "pytest-basetemp",
    "__pycache__",
    "node_modules",
    "data",
    "logs",
    "vault",
    "reports",
    "backups",
    "dist",
    "build",
    "htmlcov",
}
EXCLUDED_DIR_PREFIXES = ("pytest-cache-files-", "tmp-test-write-check", "write_probe_")
EXCLUDED_DIR_SUFFIXES = (".egg-info",)
EXCLUDED_FILES = {".env"}
EXCLUDED_SUFFIXES = {".pyc", ".sqlite3", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}
FORBIDDEN_TERMS = [
    _term("dark", "boy"),
    _term("dark", "_philosopher", "_bot"),
    _term("telegram", "-journal", "-companion"),
    _term("telegram", "_journal", "_companion"),
    _term("founder", "_memory", "_backup"),
    _term("deep", "seek"),
    _term("c:", "\\users", "\\surya"),
    _term("c:/", "users", "/surya"),
]
SECRET_PATTERNS = [
    re.compile(r"TELEGRAM_BOT_TOKEN\s*=\s*\d+:[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
    re.compile(r"(?i)(api_key|jwt_secret|auth_token|bot_token|password)\s*=\s*['\"][^'\"]{24,}['\"]"),
]


def iter_files(root: Path = ROOT):
    for dirpath, dirnames, filenames in walk(root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in EXCLUDED_DIRS
            and not dirname.endswith(EXCLUDED_DIR_SUFFIXES)
            and not any(dirname.startswith(prefix) for prefix in EXCLUDED_DIR_PREFIXES)
        ]
        for filename in filenames:
            path = Path(dirpath) / filename
            if filename in EXCLUDED_FILES:
                continue
            if path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            yield path


def main(root: Path = ROOT) -> int:
    findings: list[str] = []
    root = root.resolve()
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except PermissionError as exc:
            findings.append(f"{path.relative_to(root)}: permission error while scanning: {exc}")
            continue
        rel = path.relative_to(root)
        lower = text.lower()
        for term in FORBIDDEN_TERMS:
            if term in lower:
                findings.append(f"{rel}: forbidden term '{term}'")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{rel}: possible hardcoded secret matching {pattern.pattern}")

    if findings:
        print("Forbidden scan failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Forbidden scan passed.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify forbidden private references and secret-like values are absent."
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to inspect.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(args.root))
