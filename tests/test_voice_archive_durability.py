"""Retention is a promise, and a promise needs somewhere durable to keep it.

The voice archive writes to a filesystem path. On a container host that path is
rebuilt from the image on every deploy, so enabling retention without a mounted
volume takes a user's consent to keep their recordings and then loses them —
quietly, and only discovered when someone goes looking for audio that is gone.
Startup refuses that combination instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from thoughtpins.config import Config, config

BLOCKER = "VOICE_ARCHIVE_ENABLED requires durable storage"


@pytest.fixture
def deployment(monkeypatch):
    def apply(environment: str, *, enabled: bool, durable: bool = False, path: str = "./data/voice_archive"):
        for key, value in (
            ("ENVIRONMENT", environment),
            ("VOICE_ARCHIVE_ENABLED", enabled),
            ("VOICE_ARCHIVE_DURABLE", durable),
            ("VOICE_ARCHIVE_PATH", Path(path)),
        ):
            monkeypatch.setattr(config, key, value)
            monkeypatch.setattr(Config, key, value)

    return apply


def _blockers() -> list[str]:
    return [item for item in config.validate_startup() if BLOCKER in item]


# ------------------------------------------------------------------- refusal


def test_a_shared_deployment_will_not_boot_with_ephemeral_retention(deployment, monkeypatch):
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    deployment("production", enabled=True)
    problems = _blockers()
    assert problems, "startup accepted retention onto a disposable filesystem"
    assert "discarded on every redeploy" in problems[0]


def test_staging_is_held_to_the_same_rule(deployment, monkeypatch):
    """Staging holds real recordings from real testers."""
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    deployment("staging", enabled=True)
    assert _blockers()


def test_a_volume_that_does_not_contain_the_archive_path_is_not_enough(deployment, monkeypatch):
    """Mounting a volume elsewhere does not make this path durable."""
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/mnt/somewhere-else")
    deployment("production", enabled=True, path="./data/voice_archive")
    assert _blockers()


# ----------------------------------------------------------------- acceptance


def test_an_archive_inside_the_mounted_volume_is_accepted(deployment, monkeypatch, tmp_path):
    mount = tmp_path / "volume"
    (mount / "voice").mkdir(parents=True)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(mount))
    deployment("production", enabled=True, path=str(mount / "voice"))
    assert not _blockers()


def test_an_operator_can_assert_durability_the_check_cannot_see(deployment, monkeypatch):
    """An NFS mount or host bind is durable and unrecognisable from here."""
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    deployment("production", enabled=True, durable=True)
    assert not _blockers()


def test_retention_switched_off_is_never_blocked(deployment, monkeypatch):
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    deployment("production", enabled=False)
    assert not _blockers()


def test_local_development_keeps_its_own_disk(deployment, monkeypatch):
    """A laptop's filesystem is durable, and a self-hoster owns their storage."""
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    deployment("development", enabled=True)
    assert not _blockers()
    assert Config.voice_archive_is_durable() is True
