"""Render the release Info.plist with optional OAuth capabilities resolved."""

from __future__ import annotations

import argparse
import plistlib
from pathlib import Path

GOOGLE_SCHEME_SETTING = "$(GOOGLE_IOS_REVERSED_CLIENT_ID)"


def render_info_plist(source: Path, output: Path, *, google_enabled: bool) -> None:
    with source.open("rb") as stream:
        payload = plistlib.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Info.plist root must be a dictionary")

    if google_enabled:
        _validate_google_placeholders(payload)
    else:
        payload.pop("GIDClientID", None)
        payload.pop("GIDServerClientID", None)
        url_types = payload.get("CFBundleURLTypes")
        if isinstance(url_types, list):
            retained = [item for item in url_types if not _contains_google_scheme(item)]
            if retained:
                payload["CFBundleURLTypes"] = retained
            else:
                payload.pop("CFBundleURLTypes", None)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    try:
        temporary.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def _contains_google_scheme(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    schemes = item.get("CFBundleURLSchemes")
    return isinstance(schemes, list) and GOOGLE_SCHEME_SETTING in schemes


def _validate_google_placeholders(payload: dict[object, object]) -> None:
    expected = {
        "GIDClientID": "$(GOOGLE_IOS_CLIENT_ID)",
        "GIDServerClientID": "$(GOOGLE_IOS_SERVER_CLIENT_ID)",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"Info.plist is missing the expected {key} build setting")
    url_types = payload.get("CFBundleURLTypes")
    if not isinstance(url_types, list) or not any(_contains_google_scheme(item) for item in url_types):
        raise ValueError("Info.plist is missing the Google callback build setting")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--google-enabled", action="store_true")
    args = parser.parse_args()
    render_info_plist(args.source, args.output, google_enabled=args.google_enabled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
