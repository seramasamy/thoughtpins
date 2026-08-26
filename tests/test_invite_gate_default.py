"""The invite gate must not close by omission.

INVITE_ONLY walls every account that has not redeemed a code. It defaulted on in
staging and production, which was right during the closed beta and is a
Guideline 2.1 rejection for an open launch: a reviewer who ignores the demo
credentials registers, hits the wall, and files. The failure arrives through an
unset environment variable, so it is guarded here rather than in a runbook.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "src" / "thoughtpins" / "config.py"


def _config_with(monkeypatch, **env: str):
    """Evaluate config.py under a given environment, in isolation.

    Deliberately *not* `importlib.reload(thoughtpins.config)`. Reloading
    rebinds `thoughtpins.config.config` to a brand-new object while every
    module that did `from thoughtpins.config import config` keeps holding the
    old one. The two then disagree for the rest of the session, and a later
    test that patches one and reads the other fails for reasons that have
    nothing to do with it -- 114 of them, in a full run, all passing when run
    alone.

    Loading a private copy answers the only question these tests ask -- what
    does this file compute from this environment -- and leaves the imported
    module untouched.
    """
    for key in ("INVITE_ONLY", "ALLOW_INVITE_ONLY_LAUNCH", "ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    spec = importlib.util.spec_from_file_location("thoughtpins_config_probe", _CONFIG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_does_not_close_the_gate_by_default(monkeypatch):
    module = _config_with(monkeypatch, ENVIRONMENT="production")
    try:
        assert module.config.INVITE_ONLY is False, (
            "INVITE_ONLY defaulted on in production. Every newly registered account "
            "would hit the invite wall, including an App Store reviewer's."
        )
    finally:
        _config_with(monkeypatch)


@pytest.mark.parametrize("environment", ["staging", "production", "development"])
def test_the_gate_is_closed_only_when_asked(monkeypatch, environment):
    module = _config_with(monkeypatch, ENVIRONMENT=environment)
    try:
        assert module.config.INVITE_ONLY is False
    finally:
        _config_with(monkeypatch)


def test_the_gate_still_closes_when_set(monkeypatch):
    module = _config_with(monkeypatch, ENVIRONMENT="production", INVITE_ONLY="true")
    try:
        assert module.config.INVITE_ONLY is True, "turning the gate on must still work"
    finally:
        _config_with(monkeypatch)


def test_a_closed_gate_fails_the_deploy_check_without_acknowledgement(monkeypatch):
    import scripts.validate_production as validate_production

    # Patch the object the check actually reads. `validate_production` bound
    # `config` at its own import, and the reload-based tests above replace
    # `thoughtpins.config.config` with a new object -- so patching a freshly
    # imported `config` here would leave the check reading the old one. That
    # passed alone and failed in a full run, which is the worst way to find out.
    config = validate_production.config

    # Hold the other switch open so this test speaks only about the gate.
    monkeypatch.setattr(config, "SYSTEM_LOCKED", False)
    monkeypatch.setattr(config, "INVITE_ONLY", True)
    monkeypatch.setattr(config, "ALLOW_INVITE_ONLY_LAUNCH", False)
    problems = validate_production.invite_gate_problems()
    assert len(problems) == 1
    assert "ALLOW_INVITE_ONLY_LAUNCH" in problems[0]

    # Deliberate closed beta: allowed, because it took two variables to say so.
    monkeypatch.setattr(config, "ALLOW_INVITE_ONLY_LAUNCH", True)
    assert validate_production.invite_gate_problems() == []

    # Open launch: nothing to complain about.
    monkeypatch.setattr(config, "INVITE_ONLY", False)
    monkeypatch.setattr(config, "ALLOW_INVITE_ONLY_LAUNCH", False)
    assert validate_production.invite_gate_problems() == []


def test_a_locked_system_fails_the_deploy_check(monkeypatch):
    """The same rejection through a blunter variable.

    SYSTEM_LOCKED makes /v1/auth/register answer 403, so a reviewer cannot even
    create the account. Its default stays True -- that is right for a fresh or
    self-hosted deploy -- so the launch override is guarded here instead.
    """
    import scripts.validate_production as validate_production

    config = validate_production.config

    monkeypatch.setattr(config, "INVITE_ONLY", False)
    monkeypatch.setattr(config, "ALLOW_INVITE_ONLY_LAUNCH", False)

    monkeypatch.setattr(config, "SYSTEM_LOCKED", True)
    problems = validate_production.invite_gate_problems()
    assert any("SYSTEM_LOCKED" in p for p in problems)

    monkeypatch.setattr(config, "SYSTEM_LOCKED", False)
    assert validate_production.invite_gate_problems() == []


def test_admission_follows_the_flag(monkeypatch):
    from thoughtpins import invites

    # Same reason as above: patch the binding `invites` reads, not a fresh one.
    config = invites.config

    monkeypatch.setattr(config, "INVITE_ONLY", False)
    assert invites.invite_required() is False

    monkeypatch.setattr(config, "INVITE_ONLY", True)
    assert invites.invite_required() is True
