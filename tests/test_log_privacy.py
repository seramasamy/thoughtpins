from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_log_privacy_check_passes_current_runtime_tree() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_log_privacy.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Log privacy check passed" in result.stdout


def test_log_privacy_check_rejects_email_and_bot_user_id_templates(tmp_path: Path) -> None:
    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    bot = source / "bot"
    bot.mkdir(parents=True)
    (source / "bad_email.py").write_text(
        'from loguru import logger\nlogger.info("created email={}", "user@example.com")\n',
        encoding="utf-8",
    )
    (bot / "bad_user.py").write_text(
        'from loguru import logger\nlogger.warning("blocked user_id={}", 123)\n',
        encoding="utf-8",
    )

    assert mod.main(tmp_path) == 1


def test_log_privacy_allows_presence_flags_and_fingerprints(tmp_path: Path) -> None:
    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    source.mkdir(parents=True)
    (source / "good.py").write_text(
        'from loguru import logger\nlogger.info("registered email_present={} phone_present={} user_hash={}", True, False, "id:abc")\n',
        encoding="utf-8",
    )

    assert mod.main(tmp_path) == 0


def test_identifier_fingerprint_is_stable_and_non_revealing() -> None:
    from thoughtpins.privacy import fingerprint_identifier

    first = fingerprint_identifier("+15555550123")
    second = fingerprint_identifier("+15555550123")

    assert first == second
    assert first.startswith("id:")
    assert "+15555550123" not in first
    assert fingerprint_identifier(None) == "id:none"
