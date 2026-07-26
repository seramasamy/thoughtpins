"""Export a user's Thought Pins notes as an Obsidian-compatible vault."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_default_user  # noqa: E402
from thoughtpins.vault.exporter import VaultExporter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Thought Pins Obsidian-compatible vault.")
    parser.add_argument("--user-id", default="", help="User ID to export. Defaults to the local default user.")
    parser.add_argument("--vault-path", type=Path, default=None, help="Override output vault root path.")
    parser.add_argument("--zip", action="store_true", help="Also create a .zip package beside the vault folder.")
    parser.add_argument(
        "--obsidian-defaults", action="store_true", help="Also write safe plugin-free .obsidian defaults."
    )
    parser.add_argument("--no-clean", action="store_true", help="Do not clear managed vault files before exporting.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable export stats.")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        user_id = args.user_id.strip() or get_or_create_default_user(session=session).id
        exporter = VaultExporter(session, user_id=user_id, vault_path=args.vault_path)
        stats = exporter.export_all(
            clean=not args.no_clean, validate=True, package_zip=args.zip, obsidian_defaults=args.obsidian_defaults
        )
        payload = {
            "status": "ok" if exporter.validation_result and exporter.validation_result.ok else "validation_failed",
            "user_id": user_id,
            "vault_path": str(exporter._vault),
            "stats": stats,
            "validation": exporter.validation_result.as_dict() if exporter.validation_result else None,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Vault exported: {exporter._vault}")
            print(f"Validation: {payload['status']}")
            print(f"Markdown files: {stats.get('vault_files')}")
            if stats.get("zip_path"):
                print(f"Zip: {stats['zip_path']}")
        return 0 if payload["status"] == "ok" else 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
