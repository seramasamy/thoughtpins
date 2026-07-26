"""Seed a safe Thought Pins review account for closed-beta/App Review."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.review_seed import REVIEW_EMAIL_DEFAULT, seed_review_account  # noqa: E402
from thoughtpins.store import init_db  # noqa: E402

PASSWORD_ENV = "THOUGHTPINS_REVIEW_PASSWORD"
EMAIL_ENV = "THOUGHTPINS_REVIEW_EMAIL"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed a safe non-founder review account with fictional demo memory data."
    )
    parser.add_argument(
        "--email",
        default=os.getenv(EMAIL_ENV, REVIEW_EMAIL_DEFAULT),
        help=f"Review email. Defaults to {EMAIL_ENV} or {REVIEW_EMAIL_DEFAULT}.",
    )
    parser.add_argument(
        "--password-env", default=PASSWORD_ENV, help="Environment variable containing the review password."
    )
    parser.add_argument(
        "--no-reset", action="store_true", help="Fail instead of replacing an existing active review user."
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow seeding when ENVIRONMENT is production. Use only for a deliberate review account.",
    )
    parser.add_argument(
        "--export-vault",
        action="store_true",
        help="Export and validate the review user's Obsidian vault after seeding.",
    )
    parser.add_argument(
        "--zip-vault", action="store_true", help="Package the exported review vault as a zip. Implies --export-vault."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable seed stats.")
    args = parser.parse_args()

    password = os.getenv(args.password_env, "")
    if not password:
        print(f"FAIL: Set {args.password_env} to the review password before running this script.")
        return 2

    init_db()
    result = seed_review_account(
        email=args.email,
        password=password,
        reset=not args.no_reset,
        allow_production=args.allow_production,
        export_vault=args.export_vault or args.zip_vault,
        package_vault_zip=args.zip_vault,
    )
    payload = result.as_dict()
    payload["password_source"] = args.password_env
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Review account seeded.")
        print(f"Email: {result.email}")
        print(f"User ID: {result.user_id}")
        print(f"Password: stored from {args.password_env} (not printed)")
        print(
            "Data: "
            f"{result.entries} entries, {result.entities} entities, {result.memories} memories, "
            f"{result.documents} documents, {result.chat_messages} chat messages"
        )
        if result.vault_path:
            print(
                f"Vault: {result.vault_path} ({result.vault_files} markdown files, {result.vault_validation_errors} validation errors)"
            )
            if result.vault_zip_path:
                print(f"Vault zip: {result.vault_zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
