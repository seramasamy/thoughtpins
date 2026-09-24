from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_log_privacy_rejects_journal_content_passed_to_a_logger(tmp_path: Path) -> None:
    """Production logged "Created new entity: <name>" until September 2026."""

    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    source.mkdir(parents=True)
    (source / "leaks.py").write_text(
        "from loguru import logger\n"
        'logger.info("Created new entity: {} [{}]", display_name, entity.id)\n'
        'logger.info("Type fixed: {}", entity.surface_name)\n'
        'logger.debug("read {}", row["raw_text"])\n',
        encoding="utf-8",
    )

    assert mod.main(tmp_path) == 1


@pytest.mark.parametrize(
    "call",
    [
        'logger.info("{}", text[:200])',
        'logger.info(f"Created {display_name}")',
        'logger.warning("{}", str(entity.canonical_name))',
        'logger.info("{}", title.strip())',
        'logger.info("done", extra=summary)',
    ],
)
def test_log_privacy_sees_content_through_slices_fstrings_and_wrappers(tmp_path: Path, call: str) -> None:
    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    source.mkdir(parents=True)
    (source / "leak.py").write_text(f"from loguru import logger\n{call}\n", encoding="utf-8")

    assert mod.main(tmp_path) == 1


def test_log_privacy_allows_lengths_identifiers_and_types(tmp_path: Path) -> None:
    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    source.mkdir(parents=True)
    (source / "fine.py").write_text(
        "from loguru import logger\n"
        'logger.info("Created new entity [{}] type={}", entity.id, entity_type)\n'
        'logger.info("Extracted {} chars", len(text))\n'
        'logger.info("Channels {}", ", ".join(sorted(channels)))\n'
        'logger.warning("Failed ({})", type(exc).__name__)\n',
        encoding="utf-8",
    )

    assert mod.main(tmp_path) == 0


def test_creating_an_entity_does_not_log_its_name(isolated_db) -> None:
    from loguru import logger

    from thoughtpins.ingestion.entity_resolution import create_or_get_entity
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    captured: list[str] = []
    sink = logger.add(lambda message: captured.append(str(message)), level="DEBUG")
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("log-privacy-entity", session=session)
        entity = create_or_get_entity(
            session,
            "Marisol Quenby",
            "Marisol Quenby",
            "person",
            raw_text="Marisol Quenby called about the lease.",
            user_id=user.id,
        )
        entity_id = entity.id
        session.commit()
    finally:
        session.close()
        logger.remove(sink)

    logged = "".join(captured)
    assert entity_id in logged, "the creation should still be logged, by identifier"
    assert "Marisol" not in logged and "Quenby" not in logged


@pytest.mark.parametrize(
    "call",
    [
        'logger.error("Library ingest failed: {}", exc)',
        'logger.warning("Graph add failed: {}", str(exc)[:200])',
        'logger.warning(f"Search failed: {e}")',
        'logger.info("x " + text)',
        'logger.info("{}", ", ".join(title if flag else summary))',
        'logger.info("Created {}".format(display_name))',
        'logger.info("%s" % (text,))',
        'logger.info("{}", [entity.canonical_name])',
        'logger.opt(lazy=True).info("{}", text)',
        'logger.exception("Ingest failed: {}", exc)',
        'logger.warning("Backup failed: {}", e)',
    ],
)
def test_log_privacy_rejects_exception_text_and_formatted_content(tmp_path: Path, call: str) -> None:
    """Exception text can quote its input: SQL parameters, pydantic and JSON input."""

    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    source.mkdir(parents=True)
    (source / "leak.py").write_text(f"from loguru import logger\n{call}\n", encoding="utf-8")

    assert mod.main(tmp_path) == 1


def test_log_privacy_allows_exception_types_and_reviewed_infrastructure(tmp_path: Path) -> None:
    mod = _load_script("check_log_privacy")
    source = tmp_path / "src" / "thoughtpins"
    source.mkdir(parents=True)
    (source / "fine.py").write_text(
        'from loguru import logger\nlogger.warning("Graph add failed ({})", type(exc).__name__)\n',
        encoding="utf-8",
    )
    (source / "worker.py").write_text(
        'from loguru import logger\nlogger.warning("Celery signal registration skipped: {}", e)\n', encoding="utf-8"
    )

    assert mod.main(tmp_path) == 0
