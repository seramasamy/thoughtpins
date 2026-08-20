"""Fail when a versioned site asset changed without its cache key moving.

`site/assets/styles.css` carries a comment asking that the `?v=` on every import
move with the file it points at, because the CDN keeps serving the cached copy
otherwise. That instruction has now been missed twice, and both times the
symptom was identical and misleading: the deployment succeeds, the HTML updates
because it is not versioned, and the stylesheet behind it stays hours old. The
second time, Cloudflare served a copy with `Age: 59727` under `max-age=86400`
while the origin had the fix.

A comment cannot enforce itself. This records a digest of every asset the key
protects, so changing one without moving the key fails here rather than in
production. Regenerate with `--record` in the same commit that bumps the key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
RECORD = ROOT / "deploy" / "quality" / "site-cache-key.json"
VERSIONED_SUFFIXES = {".css", ".js"}
KEY_PATTERN = re.compile(r"\?v=([A-Za-z0-9._-]+)")


def _versioned_assets() -> list[Path]:
    return sorted(path for path in (SITE / "assets").rglob("*") if path.is_file() and path.suffix in VERSIONED_SUFFIXES)


def _digest() -> str:
    sha = hashlib.sha256()
    for path in _versioned_assets():
        sha.update(path.relative_to(SITE).as_posix().encode("utf-8"))
        # Strip the key itself so recording a new key does not change the digest
        # it is being recorded against.
        sha.update(KEY_PATTERN.sub("?v=", path.read_text(encoding="utf-8")).encode("utf-8"))
    return sha.hexdigest()


def _keys_in_use() -> set[str]:
    keys: set[str] = set()
    for path in SITE.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".css", ".js", ".webmanifest", ".json"}:
            keys.update(KEY_PATTERN.findall(path.read_text(encoding="utf-8")))
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="Store the current key and digest.")
    args = parser.parse_args()

    keys = _keys_in_use()
    if len(keys) != 1:
        print(f"Site cache key check failed: expected exactly one ?v= value, found {sorted(keys)}")
        return 1
    key = keys.pop()
    digest = _digest()

    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps({"version": key, "assets_sha256": digest}, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded cache key {key} against {len(_versioned_assets())} assets.")
        return 0

    if not RECORD.is_file():
        print(f"Site cache key check failed: {RECORD.relative_to(ROOT).as_posix()} is missing; run with --record")
        return 1

    recorded = json.loads(RECORD.read_text(encoding="utf-8"))
    if recorded.get("assets_sha256") == digest and recorded.get("version") == key:
        print(f"Site cache key check passed: {key} matches {len(_versioned_assets())} assets.")
        return 0

    if recorded.get("assets_sha256") != digest and recorded.get("version") == key:
        print(
            "Site cache key check failed: a versioned asset changed but the ?v= key did not.\n"
            f"  key still reads {key}\n"
            "  Returning visitors would keep the cached stylesheet and never see the change.\n"
            "  Bump the key across site/, then run: python scripts/check_site_cache_key.py --record"
        )
        return 1

    print(
        "Site cache key check failed: the key moved but the recorded digest was not refreshed.\n"
        f"  recorded {recorded.get('version')}, site now uses {key}\n"
        "  Run: python scripts/check_site_cache_key.py --record"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
