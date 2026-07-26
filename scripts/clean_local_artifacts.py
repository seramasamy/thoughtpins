"""Safely remove generated local Thought Pins runtime artifacts.

Default mode is a dry run. Use ``--apply`` only when preparing a clean public
package or after synthetic smoke/eval data has been verified.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]

ROOT_DIR_TARGETS = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "pytest-basetemp",
    "tmp-test-write-check",
}
ROOT_RUNTIME_STATE_TARGETS = {"backups", "data", "logs", "vault"}
ROOT_FILE_TARGETS = {".coverage"}
ROOT_PREFIX_TARGETS = ("pytest-cache-files-", "write_probe_")
TMP_DIR_TARGETS = {
    "acl-probe",
    "codex-pytest-cache",
    "codex-pytest-temp",
    "codex-smoke",
    "codex-write-check",
    "debug",
    "eval-qdrant",
    "local-evidence",
    "pytest-temp",
}
TMP_PREFIX_TARGETS = (
    "codex-final-",
    "codex-full-",
    "external-proof-self-test-",
    "frontend-resolver-",
    "pytest-run-",
    "vault-stress-",
)
OPTIONAL_REPORT_TARGETS = {"reports"}
OPTIONAL_BUILD_TARGETS = {"frontend/dist", "htmlcov"}
CACHE_SCAN_ROOTS = {"alembic", "scripts", "src", "tests"}


@dataclass(frozen=True)
class CleanupTarget:
    path: Path
    reason: str


def main(root: Path = ROOT, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean generated local Thought Pins artifacts.")
    parser.add_argument("--apply", action="store_true", help="Actually delete targets. Default is dry-run.")
    parser.add_argument(
        "--include-runtime-state", action="store_true", help="Also remove local data/, vault/, logs/, and backups/."
    )
    parser.add_argument("--include-reports", action="store_true", help="Also remove generated reports/.")
    parser.add_argument("--include-build", action="store_true", help="Also remove frontend/dist and coverage HTML.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    targets = plan_cleanup(
        root,
        include_runtime_state=args.include_runtime_state,
        include_reports=args.include_reports,
        include_build=args.include_build,
    )
    deleted: list[str] = []
    errors: list[str] = []

    if args.apply:
        for target in targets:
            try:
                _delete_target(root, target.path)
                deleted.append(_rel(root, target.path))
            except Exception as exc:
                errors.append(f"{_rel(root, target.path)}: {exc}")

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "apply": args.apply,
                    "targets": [{"path": _rel(root, item.path), "reason": item.reason} for item in targets],
                    "deleted": deleted,
                    "errors": errors,
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    else:
        action = "deleted" if args.apply else "would delete"
        if not targets:
            print("No generated local artifacts found.")
        for target in targets:
            print(f"{action}: {_rel(root, target.path)} ({target.reason})")
        if errors:
            print("Cleanup errors:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)

    return 1 if errors else 0


def plan_cleanup(
    root: Path,
    *,
    include_runtime_state: bool = False,
    include_reports: bool = False,
    include_build: bool = False,
) -> list[CleanupTarget]:
    root = root.resolve()
    targets: list[CleanupTarget] = []
    for entry in _safe_iterdir(root):
        name = entry.name
        if entry.is_dir() and name in ROOT_DIR_TARGETS:
            targets.append(CleanupTarget(entry, "generated pytest/write-probe artifact"))
        elif include_runtime_state and entry.is_dir() and name in ROOT_RUNTIME_STATE_TARGETS:
            targets.append(CleanupTarget(entry, "generated local runtime state"))
        elif entry.is_file() and name in ROOT_FILE_TARGETS:
            targets.append(CleanupTarget(entry, "generated coverage artifact"))
        elif any(name.startswith(prefix) for prefix in ROOT_PREFIX_TARGETS):
            targets.append(CleanupTarget(entry, "generated pytest/write-probe artifact"))

    tmp = root / ".tmp"
    if tmp.is_dir():
        for entry in _safe_iterdir(tmp):
            name = entry.name
            if name in TMP_DIR_TARGETS or any(name.startswith(prefix) for prefix in TMP_PREFIX_TARGETS):
                targets.append(CleanupTarget(entry, "generated scratch run"))

    for relative in CACHE_SCAN_ROOTS:
        base = root / relative
        if not base.is_dir():
            continue
        targets.extend(
            CleanupTarget(path, "generated Python bytecode cache")
            for path in base.rglob("__pycache__")
            if path.is_dir()
        )

    if include_reports:
        targets.extend(
            CleanupTarget(root / name, "generated evidence/report artifact")
            for name in OPTIONAL_REPORT_TARGETS
            if (root / name).exists()
        )
    if include_build:
        targets.extend(
            CleanupTarget(root / rel, "generated build/coverage artifact")
            for rel in OPTIONAL_BUILD_TARGETS
            if (root / rel).exists()
        )

    return sorted(_dedupe_targets(root, targets), key=lambda item: _rel(root, item.path))


def _delete_target(root: Path, path: Path) -> None:
    root = root.resolve()
    target = path.resolve()
    target.relative_to(root)
    if target == root:
        raise RuntimeError("refusing to delete repository root")
    if target.is_dir():
        shutil.rmtree(target, onerror=_retry_writable)
    elif target.exists():
        _make_writable(target)
        target.unlink()


def _retry_writable(function: Callable[[str], object], path: str, excinfo: object) -> None:
    _ = excinfo
    _make_writable(Path(path))
    function(path)


def _make_writable(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP)
    except OSError:
        pass


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except FileNotFoundError:
        return []
    except PermissionError:
        return []


def _dedupe_targets(root: Path, targets: list[CleanupTarget]) -> list[CleanupTarget]:
    seen: set[Path] = set()
    deduped: list[CleanupTarget] = []
    for target in targets:
        resolved = target.path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(target)
    return deduped


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
