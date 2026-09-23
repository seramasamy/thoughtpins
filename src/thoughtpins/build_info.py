"""Which source commit this process was built from.

`railway up` uploads a directory, not a commit, so a deployment records nothing
about what it contains. On 23 September 2026 production was found running API
and worker builds from 18 and 13 September, 14 and 18 commits behind GitHub
main, and the only evidence was the free-text note on each deployment. A green
CI run, a successful push and a 200 from /ready all looked the same either way.

`scripts/deploy_railway.py` exports exactly one pushed commit and writes
``_build_info.json`` beside this module before uploading, so the image itself
says what it was built from. Railway's GitHub-sourced builds set
``RAILWAY_GIT_COMMIT_SHA`` instead. Anything else -- a developer checkout, a
compose rehearsal, a hand-run `railway up` -- reports ``None`` rather than
guessing, because a wrong answer here is worse than an honest unknown.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

BUILD_INFO_FILENAME = "_build_info.json"
BUILD_INFO_PATH = Path(__file__).with_name(BUILD_INFO_FILENAME)

# Full SHA-1 object names only. The value is served on a public endpoint, so an
# environment variable holding anything else is dropped, never echoed.
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_ENVIRONMENT_SOURCES = ("RAILWAY_GIT_COMMIT_SHA",)


def normalize_revision(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if _COMMIT_SHA.fullmatch(candidate) else None


@lru_cache(maxsize=1)
def source_revision() -> str | None:
    """The 40-character commit this build came from, or None when unknown."""

    return _revision_from_file(BUILD_INFO_PATH) or _revision_from_environment()


def build_info_document(revision: str, *, ref: str, exported_at_utc: str) -> str:
    """Serialized build record for a deployment export; the only writer's format."""

    normalized = normalize_revision(revision)
    if normalized is None:
        raise ValueError("revision must be a full 40-character commit SHA")
    payload = {"revision": normalized, "ref": ref, "exported_at_utc": exported_at_utc}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _revision_from_file(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return normalize_revision(payload.get("revision")) if isinstance(payload, dict) else None


def _revision_from_environment() -> str | None:
    for name in _ENVIRONMENT_SOURCES:
        revision = normalize_revision(os.environ.get(name))
        if revision:
            return revision
    return None
