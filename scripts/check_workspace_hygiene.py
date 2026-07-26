"""Check that local runtime/build artifacts stay outside public packages."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_public_export  # noqa: E402

GITIGNORE_REQUIRED = {
    "__pycache__/",
    "*.py[cod]",
    ".env",
    ".tmp/",
    ".ms-playwright/",
    ".deps/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "pytest-cache-files-*/",
    "tmp-test-write-check/",
    "pytest-basetemp/",
    "write_probe_*/",
    ".coverage",
    "/htmlcov/",
    ".venv/",
    "/data/",
    "/logs/",
    "/vault/",
    "/reports/",
    "/backups/",
    "founder/private/",
    "*.sqlite3",
    "*.log",
    "frontend/node_modules/",
    "frontend/dist/",
    "mobile/android/local.properties",
}

DOCKERIGNORE_REQUIRED = {
    "__pycache__",
    "*.pyc",
    ".env",
    ".env.*",
    ".tmp",
    ".ms-playwright",
    ".deps",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "pytest-cache-files-*",
    "tmp-test-write-check",
    "pytest-basetemp/",
    "write_probe_*/",
    ".coverage",
    "htmlcov/**",
    ".venv",
    "data/**",
    "logs/**",
    "vault/**",
    "reports/**",
    "backups/**",
    "founder/private",
    "*.sqlite3",
    "*.log",
    "frontend/node_modules",
    "frontend/dist",
    "mobile/android/local.properties",
}

PUBLIC_EXCLUDED_DIRS_REQUIRED = {
    ".deps",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
    ".ms-playwright",
    ".venv",
    "__pycache__",
    "backups",
    "build",
    "data",
    "dist",
    "htmlcov",
    "logs",
    "node_modules",
    "pytest-basetemp",
    "reports",
}
ROOT_ONLY_GENERATED_DIRS = {"backups", "data", "logs", "reports", "vault"}
ANYWHERE_GENERATED_DIRS = {"__pycache__", "build", "dist", "htmlcov", "node_modules"}
PUBLIC_EXCLUDED_PREFIXES_REQUIRED = {"pytest-cache-files-", "tmp-test-write-check", "write_probe_"}
PUBLIC_EXCLUDED_DIR_SUFFIXES_REQUIRED = {".egg-info"}
PUBLIC_EXCLUDED_FILES_REQUIRED = {".env", ".coverage", "local.properties"}
PUBLIC_EXCLUDED_SUFFIXES_REQUIRED = {".log", ".pyc", ".sqlite3", ".zip"}


def main(root: Path = ROOT) -> int:
    findings: list[str] = []
    check_ignore_alignment(root, findings)
    check_public_export_alignment(findings)
    check_public_manifest_excludes_generated_state(root, findings)
    check_top_level_generated_state_is_ignored(root, findings)

    if findings:
        print("Workspace hygiene check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Workspace hygiene check passed.")
    return 0


def check_ignore_alignment(root: Path, findings: list[str]) -> None:
    gitignore = _read_ignore_file(root / ".gitignore", findings)
    dockerignore = _read_ignore_file(root / ".dockerignore", findings)
    _require_entries(".gitignore", gitignore, GITIGNORE_REQUIRED, findings)
    _require_entries(".dockerignore", dockerignore, DOCKERIGNORE_REQUIRED, findings)


def check_public_export_alignment(findings: list[str]) -> None:
    _require_values(
        "check_public_export.EXCLUDED_DIRS",
        set(check_public_export.EXCLUDED_DIRS),
        PUBLIC_EXCLUDED_DIRS_REQUIRED,
        findings,
    )
    _require_values(
        "check_public_export.EXCLUDED_DIR_PREFIXES",
        set(check_public_export.EXCLUDED_DIR_PREFIXES),
        PUBLIC_EXCLUDED_PREFIXES_REQUIRED,
        findings,
    )
    _require_values(
        "check_public_export.EXCLUDED_DIR_SUFFIXES",
        set(check_public_export.EXCLUDED_DIR_SUFFIXES),
        PUBLIC_EXCLUDED_DIR_SUFFIXES_REQUIRED,
        findings,
    )
    _require_values(
        "check_public_export.EXCLUDED_FILES",
        set(check_public_export.EXCLUDED_FILES),
        PUBLIC_EXCLUDED_FILES_REQUIRED,
        findings,
    )
    _require_values(
        "check_public_export.EXCLUDED_SUFFIXES",
        set(check_public_export.EXCLUDED_SUFFIXES),
        PUBLIC_EXCLUDED_SUFFIXES_REQUIRED,
        findings,
    )


def check_public_manifest_excludes_generated_state(root: Path, findings: list[str]) -> None:
    manifest = check_public_export.build_public_export_manifest(root)
    files = manifest.get("files", [])
    if not isinstance(files, list):
        findings.append("public export manifest has invalid files payload")
        return
    for item in files:
        if not isinstance(item, dict):
            findings.append("public export manifest contains a non-object file entry")
            continue
        rel = str(item.get("path", ""))
        if _is_generated_public_path(rel):
            findings.append(f"public export manifest includes generated/local path: {rel}")


def check_top_level_generated_state_is_ignored(root: Path, findings: list[str]) -> None:
    root_entries = {entry.name for entry in root.iterdir()}
    generated = sorted(name for name in root_entries if _is_generated_root_name(name))
    if not generated:
        return
    gitignore = _read_ignore_file(root / ".gitignore", findings)
    dockerignore = _read_ignore_file(root / ".dockerignore", findings)
    for name in generated:
        if not _matches_ignore(name, gitignore):
            findings.append(f"generated top-level path is not covered by .gitignore: {name}")
        if not _matches_ignore(name, dockerignore):
            findings.append(f"generated top-level path is not covered by .dockerignore: {name}")


def _read_ignore_file(path: Path, findings: list[str]) -> set[str]:
    if not path.is_file():
        findings.append(f"missing ignore file: {path.name}")
        return set()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            entries.add(clean)
    return entries


def _require_entries(label: str, actual: set[str], required: set[str], findings: list[str]) -> None:
    _require_values(label, actual, required, findings)


def _require_values(label: str, actual: set[str], required: set[str], findings: list[str]) -> None:
    missing = sorted(required - actual)
    for value in missing:
        findings.append(f"{label} missing generated-artifact exclusion: {value}")


def _is_generated_public_path(rel: str) -> bool:
    path = PurePosixPath(rel)
    parts = path.parts
    if not parts:
        return False
    if parts[0] in ROOT_ONLY_GENERATED_DIRS:
        return True
    if any(part in ANYWHERE_GENERATED_DIRS for part in parts):
        return True
    if any(part.endswith(tuple(PUBLIC_EXCLUDED_DIR_SUFFIXES_REQUIRED)) for part in parts):
        return True
    if any(any(part.startswith(prefix) for prefix in PUBLIC_EXCLUDED_PREFIXES_REQUIRED) for part in parts):
        return True
    if path.name in PUBLIC_EXCLUDED_FILES_REQUIRED:
        return True
    return path.suffix.lower() in PUBLIC_EXCLUDED_SUFFIXES_REQUIRED


def _is_generated_root_name(name: str) -> bool:
    if (
        name in PUBLIC_EXCLUDED_DIRS_REQUIRED
        or name in ROOT_ONLY_GENERATED_DIRS
        or name in PUBLIC_EXCLUDED_FILES_REQUIRED
    ):
        return True
    return any(name.startswith(prefix) for prefix in PUBLIC_EXCLUDED_PREFIXES_REQUIRED)


def _matches_ignore(name: str, patterns: set[str]) -> bool:
    normalized = name.rstrip("/")
    for pattern in patterns:
        clean = pattern.lstrip("/").rstrip("/")
        if clean.endswith("/**"):
            clean = clean[:-3]
        if clean == normalized:
            return True
        if clean.endswith("*") and normalized.startswith(clean[:-1]):
            return True
        if clean.startswith("*.") and normalized.endswith(clean[1:]):
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
