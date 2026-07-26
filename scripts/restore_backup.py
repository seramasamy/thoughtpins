"""Restore a Thought Pins backup zip into a target directory."""

from __future__ import annotations

import argparse
import json

from thoughtpins.backup import restore_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a Thought Pins backup into a safe target directory.")
    parser.add_argument("backup_zip", help="Path to thoughtpins_backup_*.zip")
    parser.add_argument("--target", required=True, help="Empty directory to extract into")
    parser.add_argument("--overwrite", action="store_true", help="Allow extracting into a non-empty target")
    args = parser.parse_args()

    target = restore_backup(args.backup_zip, target_root=args.target, overwrite=args.overwrite)
    manifest = target / "manifest.json"
    print(f"Restored backup to: {target}")
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            print(f"Backup created_at_utc: {payload.get('created_at_utc')}")
            print(f"Included roots: {', '.join(payload.get('included_roots', []))}")
        except Exception:
            print("Manifest exists but could not be parsed.")
    print("Inspect the restored files before copying them into an active app directory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
