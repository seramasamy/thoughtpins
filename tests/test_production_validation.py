from __future__ import annotations

import importlib.util
from pathlib import Path

from thoughtpins.config import graph_backend_problems

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "thoughtpins_validate_production",
    ROOT / "scripts" / "validate_production.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
oauth_web_build_problems = MODULE.oauth_web_build_problems


def test_oauth_web_build_allows_disabled_providers() -> None:
    assert oauth_web_build_problems([], [], {}) == []


def test_oauth_web_build_requires_enabled_provider_ids() -> None:
    problems = oauth_web_build_problems(["google-web"], ["apple-web"], {})
    assert problems == [
        "VITE_GOOGLE_CLIENT_ID is required when Google OAuth is enabled for the web app.",
        "VITE_APPLE_CLIENT_ID is required when Apple OAuth is enabled for the web app.",
    ]


def test_oauth_web_build_rejects_ids_outside_backend_allowlists() -> None:
    problems = oauth_web_build_problems(
        ["google-web"],
        ["apple-web"],
        {
            "VITE_GOOGLE_CLIENT_ID": "wrong-google",
            "VITE_APPLE_CLIENT_ID": "wrong-apple",
        },
    )
    assert problems == [
        "VITE_GOOGLE_CLIENT_ID must be included in GOOGLE_OAUTH_CLIENT_IDS.",
        "VITE_APPLE_CLIENT_ID must be included in APPLE_OAUTH_CLIENT_IDS.",
    ]


def test_oauth_web_build_accepts_matching_ids() -> None:
    assert (
        oauth_web_build_problems(
            ["google-ios", "google-web"],
            ["apple-ios", "apple-web"],
            {
                "VITE_GOOGLE_CLIENT_ID": "google-web",
                "VITE_APPLE_CLIENT_ID": "apple-web",
            },
        )
        == []
    )


def test_production_graph_backend_requires_verified_local_lifecycle() -> None:
    assert graph_backend_problems("internal_sql", False) == []
    assert graph_backend_problems("graphiti", False)
    assert graph_backend_problems("internal_sql", True)


def test_runtime_startup_rejects_external_graph_in_production(monkeypatch) -> None:
    from thoughtpins.config import Config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "GRAPH_PROVIDER", "graphiti")
    monkeypatch.setattr(Config, "GRAPH_SHADOW_ENABLED", False)

    problems = Config.validate_startup()

    assert any("External graph backends are evaluation-only" in problem for problem in problems)


def test_runtime_startup_requires_remote_authenticated_vector_store(monkeypatch) -> None:
    from thoughtpins.config import Config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "VECTOR_MODE", "qdrant_local")
    monkeypatch.setattr(Config, "QDRANT_URL", "")
    monkeypatch.setattr(Config, "QDRANT_API_KEY", "")
    monkeypatch.setattr(Config, "VECTOR_HEALTHCHECK_LIVE", False)

    problems = Config.validate_startup()

    assert "VECTOR_MODE must be qdrant_remote outside local development." in problems
    assert "QDRANT_URL must be set when VECTOR_MODE=qdrant_remote." in problems
    assert "QDRANT_API_KEY must be set when VECTOR_MODE=qdrant_remote." in problems
    assert "VECTOR_HEALTHCHECK_LIVE must be true outside local development." in problems


def test_runtime_startup_requires_bounded_worker_recovery_interval(monkeypatch) -> None:
    from thoughtpins.config import Config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "WORKER_RECOVERY_INTERVAL_SECONDS", 3_601)

    problems = Config.validate_startup()

    assert "WORKER_RECOVERY_INTERVAL_SECONDS must be between 10 and 3600." in problems
