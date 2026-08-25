"""Client-facing URL hygiene for configuration values.

Separated from `config.py` because that module is at its size budget, and
because this is one self-contained question: is a configured value fit to hand
to a client?
"""

from __future__ import annotations

import re

# A drive-letter path (C:/..., D:\...) or a UNC share (\\server\share).
_SHELL_MANGLED_PATH = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


def is_shell_mangled_path(value: str) -> bool:
    """Whether a configured URL was rewritten into a filesystem path by a shell.

    Git Bash and MSYS on Windows rewrite a bare leading-slash argument into a
    Windows path before the program ever sees it, so setting `WEB_APP_URL=/app`
    from that shell stores `C:/Program Files/Git/app`. Production served exactly
    that: it reaches every client through `/v1/client-config`, where all three
    apps read `store_urls` to build an update link, and the web app prints it
    verbatim in its legal screen.

    Set such values with `MSYS_NO_PATHCONV=1`, or give a full https:// URL.
    """
    return bool(_SHELL_MANGLED_PATH.match((value or "").strip()))


def public_client_url(value: str | None) -> str | None:
    """A URL fit to hand a client, or None when the configured value is not one.

    Serving nothing is better than serving a path that goes nowhere: a client
    given None hides its update link, while one given a Windows path shows it
    to the person.
    """
    candidate = (value or "").strip()
    if not candidate or is_shell_mangled_path(candidate):
        return None
    return candidate
