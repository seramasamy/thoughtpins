"""Who may use the product once they have registered.

Separated from `config.py` because that module is at its size budget, and
because admission is one self-contained question whose history is worth keeping
next to the values themselves.

Two independent switches can each wall a brand-new account:

* `INVITE_ONLY` -- anyone may register, but only a redeemed code opens the
  product.
* `SYSTEM_LOCKED` -- `/v1/auth/register` answers 403 outright.

Both used to default closed, so a deploy that lost an environment variable
stayed shut. That was the right failure direction during the closed beta and is
the wrong one for a public App Store build: review depends on a reviewer being
able to register and use the app, and reviewers routinely ignore demo
credentials. A production deploy that lost `INVITE_ONLY=false` would wall every
new account -- a Guideline 2.1 rejection arriving through an unset variable.

`INVITE_ONLY` is open by default now. `SYSTEM_LOCKED` still defaults closed,
which is correct for a fresh self-hosted install that nobody has configured
yet. Neither is left to chance: `scripts/validate_production.py` refuses a
production deploy that closes either one, unless
`ALLOW_INVITE_ONLY_LAUNCH` records that a closed beta is intended.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class AdmissionDefaults:
    """The admission switches, read once at configuration import."""

    invite_only: bool
    allow_invite_only_launch: bool
    system_locked: bool


def read_admission_defaults(env_bool: Callable[[str, bool], bool]) -> AdmissionDefaults:
    """Read the admission switches with the caller's environment parser.

    The parser is passed in rather than reimplemented so that one module owns
    how an environment string becomes a bool.
    """
    return AdmissionDefaults(
        invite_only=env_bool("INVITE_ONLY", False),
        # Deliberate acknowledgement that a closed beta is intended. Only read
        # by the pre-deploy check; nothing in the running service consults it.
        allow_invite_only_launch=env_bool("ALLOW_INVITE_ONLY_LAUNCH", False),
        system_locked=env_bool("SYSTEM_LOCKED", True),
    )
