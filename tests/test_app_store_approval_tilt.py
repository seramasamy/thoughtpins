from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker_module():
    path = ROOT / "scripts" / "check_app_store_approval_tilt.py"
    spec = importlib.util.spec_from_file_location("check_app_store_approval_tilt", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_store_approval_tilt_check_passes(built_frontend) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_app_store_approval_tilt.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "App Store approval tilt check passed." in result.stdout


def test_approval_tilt_rejects_private_adapter_flags_in_client_config(tmp_path: Path) -> None:
    mod = _checker_module()
    original_root = mod.ROOT
    fake_root = tmp_path
    metadata = fake_root / "src" / "thoughtpins" / "api_routes"
    metadata.mkdir(parents=True)
    (metadata / "metadata.py").write_text(
        'ai_processing="configured"\ntelegram_enabled=True\n',
        encoding="utf-8",
    )
    for rel in mod.PUBLIC_CLIENT_FILES:
        path = fake_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")

    failures: list[str] = []
    try:
        mod.ROOT = fake_root
        mod._check_public_client_config(failures)
    finally:
        mod.ROOT = original_root

    assert any("telegram_enabled" in failure for failure in failures)


def test_approval_tilt_rejects_missing_private_adapter_packet_boundary() -> None:
    mod = _checker_module()
    failures: list[str] = []
    original_json = mod._json
    mod._json = lambda _relative, _failures: {
        "private_adapters": {"personal_chat_adapter": {"included_in_store_builds": True}},
        "public_build_exclusions": {},
    }
    try:
        mod._check_private_adapter_packet(failures)
    finally:
        mod._json = original_json

    assert any("store builds" in failure for failure in failures)


def test_approval_tilt_rejects_provider_specific_source_marker(tmp_path: Path) -> None:
    mod = _checker_module()
    original_root = mod.ROOT
    original_dirs = mod.PROVIDER_NEUTRAL_DIRS
    fake_root = tmp_path
    source = fake_root / "src" / "thoughtpins" / "llm"
    source.mkdir(parents=True)
    forbidden_provider = "".join(map(chr, (100, 101, 101, 112, 115, 101, 101, 107)))
    (source / "adapter.py").write_text(f"provider = '{forbidden_provider}'\n", encoding="utf-8")

    failures: list[str] = []
    try:
        mod.ROOT = fake_root
        mod.PROVIDER_NEUTRAL_DIRS = ("src",)
        mod._check_provider_neutral_source(failures)
    finally:
        mod.ROOT = original_root
        mod.PROVIDER_NEUTRAL_DIRS = original_dirs

    assert any("provider-specific" in failure for failure in failures)
