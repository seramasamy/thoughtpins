"""Clear local Thought Pins memory/library content after creating a backup."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.memory.reset import clear_memory_data  # noqa: E402
from thoughtpins.store import get_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clear journal/library memory data while preserving users/auth config."
    )
    parser.add_argument("--yes", action="store_true", help="Required to execute deletion.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted.")
    parser.add_argument("--skip-backup", action="store_true", help="Do not create a pre-clear backup.")
    parser.add_argument("--keep-files", action="store_true", help="Do not clear vault/reports/cache files.")
    parser.add_argument("--keep-vectors", action="store_true", help="Do not reset the vector index.")
    parser.add_argument(
        "--delete-book-folder",
        type=Path,
        default=None,
        help="Optional public-domain test book folder to remove.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Refusing to delete without --yes. Run with --dry-run first to inspect counts.")
        return 2

    session = get_session()
    try:
        stats = clear_memory_data(
            session,
            dry_run=args.dry_run,
            make_backup=not args.skip_backup,
            clear_files=not args.keep_files,
            reset_vectors=not args.keep_vectors,
            delete_book_folder=args.delete_book_folder,
        )
    finally:
        session.close()

    payload = asdict(stats)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"dry_run: {stats.dry_run}")
        if stats.backup_path:
            print(f"backup: {stats.backup_path}")
        print("deleted rows:")
        for table, count in stats.deleted_rows.items():
            print(f"- {table}: {count}")
        print("remaining rows:")
        for table, count in stats.remaining_rows.items():
            print(f"- {table}: {count}")
        print(f"vector_reset: {stats.vector_reset}")
        if stats.files_cleared:
            print("files cleared:")
            for item in stats.files_cleared:
                print(f"- {item}")
        if stats.files_skipped:
            print("files skipped:")
            for item in stats.files_skipped:
                print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
