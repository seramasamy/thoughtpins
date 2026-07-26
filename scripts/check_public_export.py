"""Check that the repo can be exported without local/private state.

This is stricter than `.gitignore` because it walks the candidate public tree
and fails on obvious secrets, founder-private paths, old project names, or
runtime folders that should never be uploaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from os import walk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


PUBLIC_DIRS = {
    ".github",
    "alembic",
    "deploy",
    "docs",
    "founder",
    "frontend",
    "load",
    "mobile",
    "scripts",
    "site",
    "src",
    "tests",
}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".deps",
    ".tmp",
    ".ms-playwright",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "backups",
    "build",
    "data",
    "dist",
    "htmlcov",
    "logs",
    "node_modules",
    "reports",
    "pytest-basetemp",
}
EXCLUDED_DIR_PREFIXES = ("pytest-cache-files-", "tmp-test-write-check", "write_probe_")
EXCLUDED_DIR_SUFFIXES = (".egg-info",)
EXCLUDED_FILES = {
    ".env",
    ".coverage",
    "local.properties",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".log",
    ".pdf",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
    ".zip",
}
PUBLIC_BINARY_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
PUBLIC_BINARY_PREFIXES = (
    "frontend/public/assets/",
    "mobile/android/thoughtpins-app/src/main/res/",
    "mobile/ios/ThoughtPinsNative/Resources/Assets.xcassets/",
    "site/assets/",
)
ALLOWED_FOUNDER_PUBLIC_FILES = {
    "founder/README.md",
    "founder/TELEGRAM_RUNBOOK.md",
}
REQUIRED_PUBLIC_FILES = {
    "AGENTS.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "SUPPORT.md",
    "pyproject.toml",
    "requirements-prod.lock",
    "uv.lock",
    "frontend/public/assets/thought-pins-icon-1024.png",
    "mobile/ios/ThoughtPinsNative/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png",
    "mobile/android/gradle/verification-metadata.xml",
    "site/assets/apple-touch-icon.png",
    "scripts/create_public_export.py",
    "Dockerfile",
    "docker-compose.yml",
    "alembic.ini",
    ".env.example",
    ".env.production.example",
    ".env.staging.example",
    "docs/architecture/PLATFORM_CODEBASE_STRATEGY.md",
    "docs/release/PRIVACY_AND_STORE_READINESS.md",
    "docs/operations/PRODUCTION_RUNBOOK.md",
    "docs/release/APP_REVIEW_RISK_REGISTER.md",
    "docs/architecture/TECHNICAL_DEBT_REGISTER.md",
    "docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md",
    "docs/release/FREE_LAUNCH_POLICY.md",
    "docs/release/OPEN_SOURCE_RELEASE_CHECKLIST.md",
}
FORBIDDEN_PATH_PARTS = {
    _term("founder", "/private"),
    _term("telegram", "-journal", "-companion"),
    _term("founder", "_memory", "_backup"),
    _term("dark", "_philosopher", "_bot"),
}
FORBIDDEN_TEXT = {
    _term("dark", "boy"),
    _term("dark", "_philosopher", "_bot"),
    _term("telegram", "-journal", "-companion"),
    _term("telegram", "_journal", "_companion"),
    _term("founder", "_memory", "_backup"),
    _term("c:", "\\users", "\\surya"),
    _term("c:/", "users", "/surya"),
}
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"(?i)(api_key|jwt_secret|auth_token|bot_token|password)\s*=\s*['\"][^'\"]{24,}['\"]"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify public-export hygiene.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to inspect.")
    parser.add_argument(
        "--write-manifest",
        type=Path,
        help=(
            "Write a deterministic JSON manifest of the checked public tree. "
            "The manifest uses repo-relative paths only."
        ),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    findings: list[str] = []
    scanned_files = 0
    scanned_bytes = 0

    if not (root / "src" / "thoughtpins").is_dir():
        findings.append("missing src/thoughtpins package")
    for rel in REQUIRED_PUBLIC_FILES:
        if not (root / rel).exists():
            findings.append(f"missing required public file: {rel}")
    _check_founder_public_surface(root, findings)

    for path in _candidate_files(root):
        rel = path.relative_to(root).as_posix()
        rel_lower = rel.lower()
        if any(part in rel_lower for part in FORBIDDEN_PATH_PARTS):
            findings.append(f"{rel}: forbidden path for public export")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except PermissionError as exc:
            findings.append(f"{rel}: permission error while scanning: {exc}")
            continue
        scanned_files += 1
        scanned_bytes += len(text.encode("utf-8", errors="ignore"))
        lower = text.lower()
        for term in FORBIDDEN_TEXT:
            if term in lower:
                findings.append(f"{rel}: forbidden private reference '{term}'")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{rel}: possible hardcoded secret")

    if findings:
        print("Public export check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    if args.write_manifest:
        manifest = build_public_export_manifest(root)
        destination = args.write_manifest
        if not destination.is_absolute():
            destination = root / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Public export manifest written: {destination}")
    print(f"Public export check passed: {scanned_files} text files, {scanned_bytes // 1024} KiB inspected.")
    return 0


def build_public_export_manifest(root: Path) -> dict[str, object]:
    """Build a public-export manifest without leaking local absolute paths."""

    resolved_root = root.resolve()
    files: list[dict[str, object]] = []
    total_bytes = 0
    for path in sorted(_candidate_files(resolved_root), key=lambda item: item.relative_to(resolved_root).as_posix()):
        rel = path.relative_to(resolved_root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": rel, "bytes": size, "sha256": digest})

    return {
        "app": "Thought Pins",
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "included_roots": sorted(PUBLIC_DIRS),
        "excluded_roots": sorted(EXCLUDED_DIRS),
        "excluded_directory_suffixes": sorted(EXCLUDED_DIR_SUFFIXES),
        "excluded_files": sorted(EXCLUDED_FILES),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "public_binary_suffixes": sorted(PUBLIC_BINARY_SUFFIXES),
        "public_binary_prefixes": sorted(PUBLIC_BINARY_PREFIXES),
        "required_public_files": sorted(REQUIRED_PUBLIC_FILES),
        "founder_public_files": sorted(ALLOWED_FOUNDER_PUBLIC_FILES),
        "files": files,
    }


def _check_founder_public_surface(root: Path, findings: list[str]) -> None:
    founder = root / "founder"
    if not founder.exists():
        return
    for path in founder.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        rel_lower = rel.lower()
        if any(part in rel_lower for part in FORBIDDEN_PATH_PARTS):
            continue
        if rel not in ALLOWED_FOUNDER_PUBLIC_FILES:
            allowed = ", ".join(sorted(ALLOWED_FOUNDER_PUBLIC_FILES))
            findings.append(f"{rel}: founder public surface is restricted to {allowed}")


def _candidate_files(root: Path):
    for dirpath, dirnames, filenames in walk(root):
        current = Path(dirpath)
        rel_parts = current.relative_to(root).parts if current != root else ()
        dirnames[:] = [dirname for dirname in dirnames if _should_descend(dirname, rel_parts)]
        if current == root:
            dirnames[:] = [dirname for dirname in dirnames if dirname in PUBLIC_DIRS or dirname.startswith(".github")]
        for filename in filenames:
            path = current / filename
            if path.is_symlink():
                continue
            if filename in EXCLUDED_FILES:
                continue
            if path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() in PUBLIC_BINARY_SUFFIXES and not relative.startswith(PUBLIC_BINARY_PREFIXES):
                continue
            yield path


def _should_descend(dirname: str, rel_parts: tuple[str, ...]) -> bool:
    if dirname in EXCLUDED_DIRS:
        return False
    if dirname.endswith(EXCLUDED_DIR_SUFFIXES):
        return False
    if not rel_parts and dirname == "vault":
        return False
    if any(dirname.startswith(prefix) for prefix in EXCLUDED_DIR_PREFIXES):
        return False
    next_rel = "/".join((*rel_parts, dirname)).lower()
    return not any(part in next_rel for part in FORBIDDEN_PATH_PARTS)


if __name__ == "__main__":
    sys.exit(main())
