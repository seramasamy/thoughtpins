"""A running process must be able to say which commit it was built from.

Production once ran API and worker builds 14 and 18 commits behind GitHub main,
and a green CI run, a successful push and a 200 from /ready all looked the same
as a current deployment. These tests pin the three places a revision is read:
the process itself, the worker's heartbeat, and the public health endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from thoughtpins import build_info

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"


@pytest.fixture(autouse=True)
def fresh_revision_cache():
    build_info.source_revision.cache_clear()
    yield
    build_info.source_revision.cache_clear()


def _stamp(tmp_path: Path, revision: str) -> Path:
    path = tmp_path / build_info.BUILD_INFO_FILENAME
    path.write_text(build_info.build_info_document(revision, ref="origin/main", exported_at_utc="now"), "utf-8")
    return path


def test_the_deployment_stamp_names_the_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_INFO_PATH", _stamp(tmp_path, SHA.upper()))
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", OTHER_SHA)

    # The stamp describes the image's contents, so it outranks the platform.
    assert build_info.source_revision() == SHA


def test_railway_github_builds_fall_back_to_the_platform_variable(tmp_path, monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_INFO_PATH", tmp_path / "absent.json")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", OTHER_SHA)

    assert build_info.source_revision() == OTHER_SHA


@pytest.mark.parametrize("value", ["main", "0123456", SHA + "0", "<script>alert(1)</script>", " "])
def test_anything_but_a_full_sha_reads_as_unknown(tmp_path, monkeypatch, value):
    """The value is served publicly, so an environment variable is never echoed."""

    monkeypatch.setattr(build_info, "BUILD_INFO_PATH", tmp_path / "absent.json")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", value)

    assert build_info.source_revision() is None


def test_a_damaged_stamp_reads_as_unknown(tmp_path, monkeypatch):
    stamp = tmp_path / build_info.BUILD_INFO_FILENAME
    stamp.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(build_info, "BUILD_INFO_PATH", stamp)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)

    assert build_info.source_revision() is None


def test_the_stamp_writer_refuses_an_abbreviated_revision():
    with pytest.raises(ValueError):
        build_info.build_info_document("0123456", ref="origin/main", exported_at_utc="now")


def test_the_stamp_is_gitignored_and_reaches_the_image():
    """Written only by the deploy script, and inside a directory the image copies."""

    root = Path(__file__).resolve().parents[1]
    relative = build_info.BUILD_INFO_PATH.relative_to(root / "src").as_posix()
    assert f"src/{relative}" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "COPY src ./src" in (root / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert not any(line.strip() in {"src", "src/", "*.json", build_info.BUILD_INFO_FILENAME} for line in dockerignore)


def test_health_reports_the_api_revision(isolated_db, monkeypatch):
    from thoughtpins.api import app

    monkeypatch.setattr("thoughtpins.api_routes.metadata.source_revision", lambda: SHA)

    body = TestClient(app).get("/health").json()

    assert body["revision"] == SHA
    assert body["status"] == "ok"


def test_ready_reports_api_and_worker_revisions_without_judging_them(isolated_db, monkeypatch):
    from thoughtpins.api import app

    monkeypatch.setattr("thoughtpins.api_routes.metadata.source_revision", lambda: SHA)
    monkeypatch.setattr(
        "thoughtpins.api_routes.metadata.build_readiness_checks",
        lambda: {
            "db": {"status": "ok"},
            "redis": {"status": "ok"},
            "worker": {"status": "ok", "revision": OTHER_SHA},
            "vector": {"status": "ok"},
        },
    )

    response = TestClient(app).get("/ready")

    # A mixed pair is what every rolling deploy looks like for a minute.
    assert response.status_code == 200
    assert response.json()["revision"] == {"api": SHA, "worker": OTHER_SHA}


class _FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.expiry: dict[str, int] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expiry[key] = ex

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def llen(self, key: str) -> int:
        del key
        return 0


def test_the_worker_heartbeat_publishes_its_revision_with_the_same_lifetime(monkeypatch):
    pytest.importorskip("celery")
    from thoughtpins.config import config

    # Importing the worker builds its Celery app, which needs some broker.
    monkeypatch.setattr(config, "CELERY_BROKER_URL", "memory://")
    monkeypatch.setattr(config, "CELERY_RESULT_BACKEND", "cache+memory://")
    import thoughtpins.worker as worker
    from thoughtpins.jobs import WORKER_HEARTBEAT_KEY, WORKER_REVISION_KEY

    fake = _FakeRedis()
    monkeypatch.setattr(worker, "_redis_client", lambda: fake)
    monkeypatch.setattr(worker, "source_revision", lambda: SHA)

    worker.record_worker_heartbeat()

    assert fake.values[WORKER_REVISION_KEY] == SHA
    assert float(fake.values[WORKER_HEARTBEAT_KEY]) > 0
    assert fake.expiry[WORKER_REVISION_KEY] == fake.expiry[WORKER_HEARTBEAT_KEY] == config.WORKER_HEARTBEAT_TTL_SECONDS


def _celery_worker_health(monkeypatch, fake: _FakeRedis) -> dict[str, Any]:
    import redis

    from thoughtpins import jobs
    from thoughtpins.config import config

    for name, value in (("INGESTION_QUEUE_BACKEND", "celery"), ("REDIS_URL", "redis://heartbeat.invalid/0")):
        monkeypatch.setattr(config, name, value)
        monkeypatch.setattr(type(config), name, value)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *args, **kwargs: fake))
    return jobs.worker_health()


def test_worker_health_carries_the_published_revision(monkeypatch):
    from thoughtpins.jobs import WORKER_HEARTBEAT_KEY, WORKER_REVISION_KEY, _utcnow

    now = str(_utcnow().timestamp())
    health = _celery_worker_health(monkeypatch, _FakeRedis({WORKER_HEARTBEAT_KEY: now, WORKER_REVISION_KEY: SHA}))

    assert health["status"] == "ok"
    assert health["revision"] == SHA


def test_a_worker_from_before_revisions_is_still_healthy(monkeypatch):
    """Mid-deploy the API is new and the worker is not; readiness must not fail."""

    from thoughtpins.jobs import WORKER_HEARTBEAT_KEY, _utcnow

    health = _celery_worker_health(monkeypatch, _FakeRedis({WORKER_HEARTBEAT_KEY: str(_utcnow().timestamp())}))

    assert health["status"] == "ok"
    assert health["revision"] is None
