"""Fail on any high or critical npm advisory that is not under a reviewed, unexpired exception.

`npm audit --audit-level=high` has no way to say "this advisory was reviewed".
When an advisory has no patched release anywhere, it fails every build until the
upstream ships a fix, and the only ways around it are to stop auditing, or to
apply npm's suggested downgrade, which can be a years-old major version.

This keeps the strict gate, with one narrow escape:
- An advisory may be excused only by an entry in
  `deploy/security/npm-audit-exceptions.json` that names it and gives a reason.
- Each entry expires within 31 days of its review, and an expired entry fails.
- Every other high or critical advisory still fails, including new advisories
  in the same package.
- An entry whose advisory no longer appears is reported, so it can be removed.

Standard library only: CI runs it before any Python environment exists.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
EXCEPTIONS_FILE = ROOT / "deploy" / "security" / "npm-audit-exceptions.json"
BLOCKING_SEVERITIES = {"high", "critical"}
MAX_EXCEPTION_DAYS = 31


def advisory_id(via: dict[str, Any]) -> str:
    url = str(via.get("url") or "")
    return url.rstrip("/").rsplit("/", 1)[-1] if url else f"npm-{via.get('source')}"


def blocking_advisories(audit: dict[str, Any]) -> dict[str, set[str]]:
    """Map each high/critical advisory id to the vulnerable packages it reaches."""
    found: dict[str, set[str]] = {}
    for package, vulnerability in (audit.get("vulnerabilities") or {}).items():
        for via in vulnerability.get("via") or []:
            # A string names another vulnerable package; its own entry lists the advisory.
            if isinstance(via, dict) and str(via.get("severity")) in BLOCKING_SEVERITIES:
                found.setdefault(advisory_id(via), set()).add(str(via.get("name") or package))
    return found


def evaluate(audit: dict[str, Any], exceptions: list[dict[str, Any]], today: date) -> tuple[list[str], list[str]]:
    """Return (failures, notes)."""
    failures: list[str] = []
    notes: list[str] = []
    active: dict[str, dict[str, Any]] = {}
    for entry in exceptions:
        problem = _entry_problem(entry)
        if problem:
            failures.append(problem)
            continue
        reviewed = date.fromisoformat(entry["reviewed_on"])
        expires = date.fromisoformat(entry["expires_on"])
        if (expires - reviewed).days > MAX_EXCEPTION_DAYS:
            failures.append(f"exception {entry['advisory']} lasts more than {MAX_EXCEPTION_DAYS} days; review it again")
        elif today > expires:
            failures.append(f"exception {entry['advisory']} expired on {expires.isoformat()}; review it again")
        else:
            active[entry["advisory"]] = entry

    advisories = blocking_advisories(audit)
    for advisory, packages in sorted(advisories.items()):
        excepted = active.get(advisory)
        if excepted is None:
            failures.append(f"{advisory} ({', '.join(sorted(packages))}) is high or critical and not excepted")
        else:
            notes.append(
                f"{advisory} ({', '.join(sorted(packages))}) excepted until {excepted['expires_on']}: {excepted['reason']}"
            )
    for advisory in sorted(set(active) - set(advisories)):
        notes.append(f"exception {advisory} no longer matches any advisory; remove it")
    return failures, notes


def _entry_problem(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return "every exception must be an object"
    for field in ("advisory", "package", "reason", "reviewed_on", "expires_on"):
        if not str(entry.get(field) or "").strip():
            return f"exception {entry.get('advisory', '?')} is missing {field}"
    try:
        date.fromisoformat(entry["reviewed_on"])
        date.fromisoformat(entry["expires_on"])
    except ValueError:
        return f"exception {entry['advisory']} has a date that is not ISO formatted"
    return None


def run_npm_audit(frontend: Path) -> dict[str, Any]:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm audit check failed: npm executable not found")
    completed = subprocess.run(
        [npm, "audit", "--json"], cwd=frontend, capture_output=True, text=True, encoding="utf-8", timeout=180
    )
    # npm exits non-zero whenever it finds anything, so the JSON decides, not the code.
    try:
        return json.loads(completed.stdout.lstrip("﻿"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"npm audit check failed: npm audit did not return JSON ({completed.returncode})") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frontend", type=Path, default=FRONTEND_DIR)
    parser.add_argument("--audit-json", type=Path, help="read a saved `npm audit --json` report instead of running npm")
    parser.add_argument("--exceptions", type=Path, default=EXCEPTIONS_FILE)
    args = parser.parse_args(argv)

    audit = (
        json.loads(args.audit_json.read_text(encoding="utf-8-sig")) if args.audit_json else run_npm_audit(args.frontend)
    )
    exceptions = json.loads(args.exceptions.read_text(encoding="utf-8")).get("exceptions", [])
    failures, notes = evaluate(audit, exceptions, date.today())
    for note in notes:
        print(f"note: {note}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        print(f"npm audit check failed: {len(failures)} failure(s).")
        return 1
    print("npm audit check passed: no high or critical advisory without a current, reviewed exception.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
