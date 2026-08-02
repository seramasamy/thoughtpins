"""Read and act on the private-launch invite queue.

Requests are stored, not mailed. This is how you read them. Against production,
point DATABASE_URL at Railway's DATABASE_PUBLIC_URL: the internal hostname only
resolves inside Railway's network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins import invite_requests  # noqa: E402
from thoughtpins.db import InviteRequest  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.tenancy import tenant_context  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the Thought Pins invite request queue.")
    parser.add_argument("--list", action="store_true", help="Show pending requests.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument("--resolve", default="", help="Mark a request id as invited.")
    parser.add_argument("--decline", default="", help="Mark a request id as declined.")
    parser.add_argument("--send-digest", action="store_true", help="Send a digest now if the limits allow.")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        if args.resolve or args.decline:
            request_id = args.resolve or args.decline
            status = invite_requests.INVITED if args.resolve else invite_requests.DECLINED
            for row in invite_requests.pending_across_tenants(session):
                if row["request_id"] != request_id:
                    continue
                with tenant_context(row["user_id"]):
                    record = session.query(InviteRequest).filter(InviteRequest.id == request_id).first()
                    if record is None:
                        break
                    record.status = status
                    session.commit()
                print(f"{request_id} marked {status}")
                return 0
            print(f"No pending request with id {request_id}")
            return 1

        if args.send_digest:
            print(json.dumps(invite_requests.maybe_send_digest(session), indent=1))
            return 0

        rows = invite_requests.pending_across_tenants(session)
        if args.json:
            print(json.dumps({"pending": len(rows), "requests": rows}, indent=1))
            return 0
        if not rows:
            print("No pending invite requests.")
            return 0
        print(f"{len(rows)} pending invite request(s)\n")
        for row in rows:
            flag = "" if row["notified"] else "  (not yet in a digest)"
            print(f"{row['requested_at_utc']}  {row['email']}{flag}")
            print(f"  id={row['request_id']}  account={row['user_id']}")
            if row["note"]:
                print(f"  note: {row['note']}")
            print()
        print("Issue a code with: python scripts/create_invite_code.py --uses 1")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
