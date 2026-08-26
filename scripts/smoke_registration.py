"""Prove that a stranger can still create an account on a deployed API.

`scripts/validate_production.py` reads configuration and refuses a deploy that
would wall new accounts. That is worth having and it is not enough: it runs
before the deploy, so it cannot see a variable someone deletes on a Tuesday
afternoon. `INVITE_ONLY` and `SYSTEM_LOCKED` both default closed for a reason,
and either one turning back on makes every self-registering App Store reviewer
hit a wall -- a Guideline 2.1 rejection arriving through an environment
variable, with nothing in the repository noticing.

A check that reads config proves config. This one registers.

It creates a throwaway account, asserts registration succeeded, asserts the
invite gate admits it, records the AI-processing acceptance the clients require
before the app is usable, and then deletes the account again. It fails loudly:
any unexpected status raises, and the traceback is the report.

Deliberately not part of the offline release gate -- it needs the network, and
an air-gapped build should not fail for that. Run it after a deploy:

    python scripts/smoke_registration.py --base-url https://api.thoughtpins.com
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from smoke_api import _expect, _json  # noqa: E402

# Twelve characters is the server minimum, and the rest of the smoke suite uses
# this same passphrase. Read through the environment the way smoke_api.py does,
# so a deployment that wants a different one does not need a code change.
SMOKE_PASSWORD = os.getenv("THOUGHTPINS_SMOKE_PASSWORD", "correct horse battery staple")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove registration works on a deployed API.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("THOUGHTPINS_BASE_URL", "http://127.0.0.1:8420"),
        help="API origin. Defaults to THOUGHTPINS_BASE_URL or the local API.",
    )
    parser.add_argument(
        "--keep-account",
        action="store_true",
        help="Do not delete the throwaway account. For debugging a failure only.",
    )
    return parser.parse_args(argv)


def _fail(message: str) -> None:
    """Stop with a sentence an operator can act on."""
    raise SystemExit(f"registration smoke FAILED: {message}")


def _check_not_locked(client: httpx.Client) -> str:
    """Read the gate's own answer before touching it, and get the legal version.

    `registration_locked` is `SYSTEM_LOCKED`, and `invite_required` is
    `INVITE_ONLY`. Reporting them here means a failure names the variable
    instead of leaving someone to guess from a 403.
    """
    config = _json(_expect(client.get("/v1/client-config"), 200))
    if config.get("registration_locked"):
        _fail("client-config reports registration_locked: SYSTEM_LOCKED is on, so /v1/auth/register answers 403")
    if config.get("invite_required"):
        _fail("client-config reports invite_required: INVITE_ONLY is on, so a new account is walled after registering")
    version = config.get("legal_document_version")
    if not isinstance(version, str) or not version:
        _fail(f"client-config has no legal_document_version: {config!r}")
    return version


def _register(client: httpx.Client, email: str) -> str:
    response = client.post("/v1/auth/register", json={"email": email, "password": SMOKE_PASSWORD})
    if response.status_code == 403:
        _fail("POST /v1/auth/register answered 403. SYSTEM_LOCKED is on. Set SYSTEM_LOCKED=false on the deployment.")
    if response.status_code == 429:
        _fail("POST /v1/auth/register was rate limited (429). Wait a minute and re-run; do not loop.")
    body = _json(_expect(response, 200))
    if body.get("status") != "ok":
        _fail(f"register did not report ok: {body!r}")
    user_id = body.get("user_id")
    if not user_id:
        _fail(f"register returned no user_id: {body!r}")
    if body.get("email_verification_required"):
        _fail(
            "register reports email_verification_required. This flow cannot complete unattended, "
            "and skipping it would make the check vacuous. Set REQUIRE_EMAIL_VERIFICATION=false."
        )
    return str(user_id)


def _login(client: httpx.Client, email: str) -> str:
    response = client.post("/v1/auth/login", json={"identifier": email, "password": SMOKE_PASSWORD})
    if response.status_code == 429:
        _fail("POST /v1/auth/login was rate limited (429). Wait a minute and re-run.")
    token = _json(_expect(response, 200)).get("access_token")
    if not token:
        _fail("login returned no access_token")
    return str(token)


def _check_admitted(client: httpx.Client, headers: dict[str, str]) -> None:
    status = _json(_expect(client.get("/v1/invites/status", headers=headers), 200))
    if status.get("admitted") is not True:
        _fail(
            f"a freshly registered account is not admitted: {status!r}. "
            "INVITE_ONLY is on; every self-registering reviewer hits the wall."
        )


def _accept_ai_disclosure(client: httpx.Client, headers: dict[str, str], version: str) -> None:
    """The clients will not let an account save anything until this is recorded.

    Registering an account nobody can use is not proof that registration works,
    so the check goes as far as the app does.
    """
    response = client.post(
        "/v1/legal/acceptances",
        headers=headers,
        json={"document": "ai_disclosure", "version": version},
    )
    _expect(response, 200)


def _delete(client: httpx.Client, headers: dict[str, str], email: str, user_id: str) -> None:
    response = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    if response.status_code != 200:
        # The one place a bare traceback is not enough: an operator has to know
        # which account to remove by hand.
        print(
            f"WARNING: could not delete the throwaway account. Remove it manually.\n"
            f"  email:   {email}\n"
            f"  user_id: {user_id}\n"
            f"  status:  {response.status_code} {response.text[:400]}",
            file=sys.stderr,
        )
        _expect(response, 200)
    body = _json(response)
    if body.get("status") != "deleted":
        _fail(f"delete did not report deleted: {body!r}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    base_url = args.base_url.rstrip("/")
    email = f"smoke-register-{uuid4().hex[:12]}@thoughtpins.com"
    print(f"registration smoke against {base_url} as {email}")

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        version = _check_not_locked(client)
        user_id = _register(client, email)
        print(f"register: ok (user_id {user_id})")
        headers = {"Authorization": f"Bearer {_login(client, email)}"}
        print("login: ok")
        # Everything after the account exists goes in a try, so a failed
        # assertion still takes the throwaway account with it. Without this an
        # aborted run leaves an orphan on production every time it fails --
        # which is exactly when it will be run repeatedly.
        try:
            _check_admitted(client, headers)
            print("invites/status: admitted")
            _accept_ai_disclosure(client, headers, version)
            print(f"ai_disclosure {version}: accepted")
        finally:
            if args.keep_account:
                print(f"delete: skipped by --keep-account; remove {email} by hand")
            else:
                _delete(client, headers, email, user_id)
                print("delete: ok")

    print("registration smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
