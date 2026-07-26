from __future__ import annotations

import importlib.util
import plistlib
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mobile" / "ios" / "ThoughtPinsNative" / "Resources" / "Info.plist"


def _module() -> ModuleType:
    path = ROOT / "scripts" / "render_ios_info_plist.py"
    spec = importlib.util.spec_from_file_location("render_ios_info_plist", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    with path.open("rb") as stream:
        value = plistlib.load(stream)
    assert isinstance(value, dict)
    return value


def test_release_plist_removes_unconfigured_google_metadata(tmp_path: Path) -> None:
    output = tmp_path / "Info.plist"
    _module().render_info_plist(SOURCE, output, google_enabled=False)

    payload = _read(output)
    assert "GIDClientID" not in payload
    assert "GIDServerClientID" not in payload
    assert "CFBundleURLTypes" not in payload
    assert payload["CFBundleDisplayName"] == "Thought Pins"


def test_release_plist_preserves_configured_google_build_settings(tmp_path: Path) -> None:
    output = tmp_path / "Info.plist"
    _module().render_info_plist(SOURCE, output, google_enabled=True)

    payload = _read(output)
    assert payload["GIDClientID"] == "$(GOOGLE_IOS_CLIENT_ID)"
    assert payload["GIDServerClientID"] == "$(GOOGLE_IOS_SERVER_CLIENT_ID)"
    assert payload["CFBundleURLTypes"][0]["CFBundleURLSchemes"] == ["$(GOOGLE_IOS_REVERSED_CLIENT_ID)"]
