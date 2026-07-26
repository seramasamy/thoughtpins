"""Validate an exported Thought Pins Obsidian-compatible vault."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.vault.validator import validate_vault  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Thought Pins Obsidian-compatible vault folder.")
    parser.add_argument("vault", type=Path, help="Path to a generated vault folder")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation output")
    args = parser.parse_args()

    result = validate_vault(args.vault)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"Vault: {result.root}")
        print(f"Markdown files checked: {result.checked_files}")
        print(f"Errors: {len(result.errors)}")
        print(f"Warnings: {len(result.warnings)}")
        for finding in result.findings:
            print(f"{finding.severity.upper()} {finding.path}: {finding.message}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
