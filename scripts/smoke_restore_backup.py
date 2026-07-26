"""Create or restore a backup into scratch space and verify it is readable."""

from __future__ import annotations

import argparse
import json

from thoughtpins.backup import smoke_restore_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Thought Pins backup restore safety.")
    parser.add_argument("--backup", help="Existing thoughtpins_backup_*.zip to verify")
    parser.add_argument("--target", help="Empty target directory to restore into")
    parser.add_argument("--keep", action="store_true", help="Keep the restored target directory")
    args = parser.parse_args()

    info = smoke_restore_backup(
        backup_path=args.backup,
        target_root=args.target,
        cleanup=not args.keep,
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "backup_path": str(info.backup_path),
                "target_path": str(info.target_path),
                "size_bytes": info.size_bytes,
                "restored_files": info.restored_files,
                "included_roots": info.included_roots,
                "cleaned_up": info.cleaned_up,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
