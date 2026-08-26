from __future__ import annotations

import importlib.util
import plistlib
from pathlib import Path
from types import ModuleType

import pytest

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


def test_enabling_google_against_the_v1_source_refuses_loudly(tmp_path: Path) -> None:
    """v1 ships no Google keys, so asking to enable Google must fail, not no-op.

    The app suppresses Google sign-in unless Sign in with Apple is offered
    alongside it (Guideline 4.8), and Apple is not configured, so the keys were
    removed rather than left resolving to empty strings. Rendering with
    --google-enabled has to say so: producing a plist that silently claims
    Google without a client ID or a callback scheme is the failure this guards.
    """
    output = tmp_path / "Info.plist"
    with pytest.raises(ValueError, match="GIDClientID"):
        _module().render_info_plist(SOURCE, output, google_enabled=True)
    assert not output.exists()


def test_configured_google_build_settings_survive_rendering(tmp_path: Path) -> None:
    """The preserve path still works, for when Google is restored.

    Built from a synthetic source rather than the shipped one, because the
    shipped one deliberately has no Google keys today. This is the shape
    AFTER_DEVELOPER_ACCOUNT.md tells you to put back.
    """
    source = tmp_path / "Source.plist"
    payload = _read(SOURCE)
    payload["GIDClientID"] = "$(GOOGLE_IOS_CLIENT_ID)"
    payload["GIDServerClientID"] = "$(GOOGLE_IOS_SERVER_CLIENT_ID)"
    payload["CFBundleURLTypes"] = [
        {"CFBundleTypeRole": "Editor", "CFBundleURLSchemes": ["$(GOOGLE_IOS_REVERSED_CLIENT_ID)"]}
    ]
    with source.open("wb") as stream:
        plistlib.dump(payload, stream)

    output = tmp_path / "Info.plist"
    _module().render_info_plist(source, output, google_enabled=True)

    rendered = _read(output)
    assert rendered["GIDClientID"] == "$(GOOGLE_IOS_CLIENT_ID)"
    assert rendered["GIDServerClientID"] == "$(GOOGLE_IOS_SERVER_CLIENT_ID)"
    assert rendered["CFBundleURLTypes"][0]["CFBundleURLSchemes"] == ["$(GOOGLE_IOS_REVERSED_CLIENT_ID)"]

    # And disabling it against that same source strips all three again.
    stripped_output = tmp_path / "Stripped.plist"
    _module().render_info_plist(source, stripped_output, google_enabled=False)
    stripped = _read(stripped_output)
    assert "GIDClientID" not in stripped
    assert "GIDServerClientID" not in stripped
    assert "CFBundleURLTypes" not in stripped
