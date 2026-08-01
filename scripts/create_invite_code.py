"""Mint a private-launch invite code.

The plaintext is printed once and never stored, so copy it before closing the
terminal. Run against production with `railway run python scripts/create_invite_code.py`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.db import InviteCode  # noqa: E402
from thoughtpins.invites import create_invite_code, format_code  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or list Thought Pins invite codes.")
    parser.add_argument("--label", default="", help="A note so codes can be told apart later.")
    parser.add_argument("--uses", type=int, default=1, help="How many accounts this code may admit.")
    parser.add_argument("--days", type=int, default=0, help="Expire after this many days. 0 means never.")
    parser.add_argument("--count", type=int, default=1, help="How many codes to mint.")
    parser.add_argument("--list", action="store_true", help="Show existing codes instead of minting.")
    parser.add_argument("--revoke", default="", help="Revoke the code with this id.")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        if args.list:
            rows = session.query(InviteCode).order_by(InviteCode.created_at_utc.desc()).all()
            if not rows:
                print("No invite codes yet.")
                return 0
            print(f"{'id':34}{'label':24}{'uses':>10}  expires        state")
            for row in rows:
                uses = f"{row.used_count}/{row.max_uses}"
                expires = row.expires_at_utc.date().isoformat() if row.expires_at_utc else "never"
                state = "revoked" if row.revoked_at_utc else ("spent" if row.used_count >= row.max_uses else "active")
                print(f"{row.id:34}{(row.label or '-'):24}{uses:>10}  {expires:14} {state}")
            return 0

        if args.revoke:
            row = session.query(InviteCode).filter(InviteCode.id == args.revoke).first()
            if not row:
                print(f"No invite code with id {args.revoke}")
                return 1
            row.revoked_at_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            session.commit()
            print(f"Revoked {row.id} ({row.label or 'no label'})")
            return 0

        expires_at = None
        if args.days > 0:
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=args.days)

        for index in range(max(1, args.count)):
            label = args.label or f"minted-{datetime.now(timezone.utc):%Y-%m-%d}"
            record, code = create_invite_code(
                session,
                label=label if args.count == 1 else f"{label}-{index + 1}",
                max_uses=args.uses,
                expires_at=expires_at,
            )
            session.commit()
            print(f"{format_code(code)}   id={record.id} uses={record.max_uses} label={record.label}")
        print("\nStore these now: only the hash is kept, so they cannot be shown again.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
