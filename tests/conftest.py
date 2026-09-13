from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import close_all_sessions

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTEST_TEMP_ROOT = PROJECT_ROOT / ".tmp" / "pytest-temp" / f"run-{uuid4().hex}"
PYTEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
for _name in ("TMP", "TEMP", "TMPDIR", "PYTEST_DEBUG_TEMPROOT"):
    os.environ[_name] = str(PYTEST_TEMP_ROOT)
tempfile.tempdir = str(PYTEST_TEMP_ROOT)


def _dispose_test_engine(engine: Engine | None) -> None:
    # Read the engine again after yield: tests may have initialized the store.
    if engine is not None:
        close_all_sessions()
        engine.dispose()


@pytest.fixture()
def telegram_bot():
    """Skip when the telegram extra is absent.

    thoughtpins.bot.handlers imports the telegram package at module scope. That
    extra pulls easyocr and whisper, which drag in torch, so CI deliberately does
    not install it and these tests are not applicable there.
    """
    return pytest.importorskip("telegram")


@pytest.fixture()
def built_frontend() -> Path:
    """Skip when the production web bundle has not been built.

    These assertions are about a build output, not about source behaviour, so
    they only mean something once `npm run build` has run.
    """
    dist = PROJECT_ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("frontend/dist is not built; run `npm run build` in frontend/")
    return dist


def _safe_node_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value)
    return safe[-120:] or "test"


@pytest.fixture()
def tmp_path(request: pytest.FixtureRequest) -> Path:
    root = PYTEST_TEMP_ROOT / "cases"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_safe_node_id(request.node.nodeid)}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


@pytest.fixture()
def isolated_db():
    import thoughtpins.store as store
    from thoughtpins.config import config

    project_root = Path(__file__).resolve().parents[1]
    db_dir = project_root / ".tmp" / "test-dbs"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / f"thoughtpins-{uuid4().hex}.sqlite3"
    postgres_test_url = os.getenv("THOUGHTPINS_TEST_DATABASE_URL", "").strip()
    config_cls = type(config)
    old_values = {
        key: (getattr(config, key), getattr(config_cls, key))
        for key in (
            "DATABASE_URL",
            "AUTO_CREATE_TABLES",
            "REQUIRE_API_AUTH",
            "SYSTEM_LOCKED",
            "PROCESS_ENTRIES_ASYNC",
            "RATE_LIMIT_ENABLED",
            "API_KEY",
            "JWT_SECRET",
            "INGESTION_QUEUE_BACKEND",
            "INGESTION_MAX_RETRIES",
            "REQUIRE_EMAIL_VERIFICATION",
            "GOOGLE_OAUTH_CLIENT_IDS",
            "APPLE_OAUTH_CLIENT_IDS",
            "APPLE_OAUTH_WEB_CLIENT_ID",
            "APPLE_OAUTH_TEAM_ID",
            "APPLE_OAUTH_KEY_ID",
            "APPLE_OAUTH_PRIVATE_KEY",
            "APPLE_OAUTH_PRIVATE_KEY_PATH",
            "APPLE_OAUTH_REDIRECT_URIS",
            "APPLE_OAUTH_TIMEOUT_SECONDS",
            "ALLOW_OAUTH_REGISTRATION",
            "DATA_ENCRYPTION_KEY",
            "VOICE_ARCHIVE_PATH",
            "TRANSCRIPTION_PROVIDER",
            "TRANSCRIPTION_API_KEY",
            "TRANSCRIPTION_BASE_URL",
            "TRANSCRIPTION_MODEL",
            "TRANSCRIPTION_TIMEOUT_SECONDS",
            "ARTICLE_FETCH_PROVIDERS",
            "LIBRARY_EXTRACT_GRAPH",
            "MAINTENANCE_MODE",
            "MAINTENANCE_MESSAGE",
            "MAINTENANCE_RETRY_AFTER_SECONDS",
            "MAINTENANCE_ALLOW_READS",
            "LLM_PROVIDER",
            "LLM_BASE_URL",
            "LLM_MODEL",
            "LLM_API_KEY",
            "LLM_HEALTHCHECK_LIVE",
            "VECTOR_MODE",
            "VECTOR_HEALTHCHECK_LIVE",
            "QDRANT_PATH",
            "OPENAI_API_KEY",
            "EMBEDDING_PROVIDER",
            "VAULT_IMPORT_PATH",
            "VAULT_IMPORT_SESSION_HOURS",
            "VAULT_UPLOAD_CHUNK_BYTES",
        )
    }

    overrides = {
        "DATABASE_URL": postgres_test_url or f"sqlite:///{db_path.as_posix()}",
        "AUTO_CREATE_TABLES": True,
        "REQUIRE_API_AUTH": False,
        "SYSTEM_LOCKED": False,
        "PROCESS_ENTRIES_ASYNC": False,
        "RATE_LIMIT_ENABLED": False,
        "API_KEY": "test-admin-key",
        "JWT_SECRET": "test-jwt-secret-that-is-at-least-32-chars",
        "INGESTION_QUEUE_BACKEND": "thread",
        "INGESTION_MAX_RETRIES": 3,
        "REQUIRE_EMAIL_VERIFICATION": False,
        "GOOGLE_OAUTH_CLIENT_IDS": [],
        "APPLE_OAUTH_CLIENT_IDS": [],
        "APPLE_OAUTH_WEB_CLIENT_ID": "",
        "APPLE_OAUTH_TEAM_ID": "",
        "APPLE_OAUTH_KEY_ID": "",
        "APPLE_OAUTH_PRIVATE_KEY": "",
        "APPLE_OAUTH_PRIVATE_KEY_PATH": "",
        "APPLE_OAUTH_REDIRECT_URIS": [],
        "APPLE_OAUTH_TIMEOUT_SECONDS": 10,
        "ALLOW_OAUTH_REGISTRATION": False,
        "DATA_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "VOICE_ARCHIVE_ENABLED": True,
        "VOICE_ARCHIVE_PATH": project_root / ".tmp" / "test-voice" / uuid4().hex,
        "TRANSCRIPTION_PROVIDER": "local",
        "TRANSCRIPTION_API_KEY": "",
        "TRANSCRIPTION_BASE_URL": "https://transcription.example.com/v1",
        "TRANSCRIPTION_MODEL": "test-transcription-model",
        "TRANSCRIPTION_LOCAL_MODEL": "tiny",
        "TRANSCRIPTION_TIMEOUT_SECONDS": 30,
        "ARTICLE_FETCH_PROVIDERS": ["local"],
        "LIBRARY_EXTRACT_GRAPH": False,
        "MAINTENANCE_MODE": False,
        "MAINTENANCE_MESSAGE": "Thought Pins is in maintenance for a short upgrade. Please try again soon.",
        "MAINTENANCE_RETRY_AFTER_SECONDS": 300,
        "MAINTENANCE_ALLOW_READS": True,
        "LLM_PROVIDER": "openai_compatible",
        "LLM_BASE_URL": "https://llm.example.com/v1",
        "LLM_MODEL": "test-chat-model",
        "LLM_API_KEY": "test-llm-key",
        "LLM_HEALTHCHECK_LIVE": False,
        "VECTOR_MODE": "memory",
        "VECTOR_HEALTHCHECK_LIVE": False,
        "QDRANT_PATH": str(project_root / ".tmp" / "test-qdrant" / uuid4().hex),
        "OPENAI_API_KEY": "",
        "EMBEDDING_PROVIDER": "local",
        "VAULT_IMPORT_PATH": project_root / ".tmp" / "test-vault-imports" / uuid4().hex,
        "VAULT_IMPORT_SESSION_HOURS": 24,
        "VAULT_UPLOAD_CHUNK_BYTES": 512 * 1024,
    }
    for key, value in overrides.items():
        setattr(config, key, value)
        setattr(config_cls, key, value)

    _dispose_test_engine(store._engine)
    store._engine = None
    store._SessionLocal = None
    if postgres_test_url:
        from thoughtpins.db import Base

        engine = store.get_engine()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        store.init_db()

    try:
        yield
    finally:
        try:
            from thoughtpins.memory.vector_store import close_vector_store

            close_vector_store()
        except Exception:
            pass
        for key, (instance_value, class_value) in old_values.items():
            setattr(config, key, instance_value)
            setattr(config_cls, key, class_value)
        _dispose_test_engine(store._engine)
        store._engine = None
        store._SessionLocal = None
        if not postgres_test_url:
            db_path.unlink(missing_ok=True)
