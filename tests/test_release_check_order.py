from __future__ import annotations

from pathlib import Path

from scripts import release_check

ROOT = Path(__file__).resolve().parents[1]


def test_release_check_builds_frontend_before_web_contract() -> None:
    source = (ROOT / "scripts" / "release_check.py").read_text(encoding="utf-8-sig")
    frontend_build = source.index("ok &= _frontend_check(step)")
    web_review = source.index('ok &= step("web review harness"')
    responsive = source.index('ok &= step("web responsive layout"')
    accessibility = source.index('ok &= step("web accessibility contract"')
    web_contract = source.index('ok &= step("web app product contract"')
    assert frontend_build < web_review < responsive < accessibility < web_contract
    assert source.count("ok &= _frontend_check(step)") == 1


def test_release_check_preflight_reports_missing_tools_by_package_name(monkeypatch) -> None:
    available = {"alembic.config", "loguru", "pytest", "sqlalchemy"}
    monkeypatch.setattr(release_check, "_module_available", available.__contains__)

    assert release_check._missing_python_modules(include_tests=True, include_quality=False) == [
        "radon",
        "uv",
        "vulture",
    ]
    assert release_check._missing_python_modules(include_tests=False, include_quality=True) == [
        "bandit",
        "mypy",
        "pip-audit",
        "radon",
        "ruff",
        "uv",
        "vulture",
    ]
