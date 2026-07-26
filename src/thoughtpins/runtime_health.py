"""Runtime dependency health checks used by API and founder diagnostics."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import func, text

from thoughtpins.article_fetch import article_fetch_health
from thoughtpins.config import config
from thoughtpins.db import IngestionJob, RawEntry
from thoughtpins.jobs import worker_health
from thoughtpins.store import get_session

HEALTHY_STATUSES = {"ok", "disabled", "configured", "warn"}


def build_deep_health_checks(user_id: str) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "db": {"status": "unknown"},
        "redis": {"status": "disabled"},
        "llm": llm_health(),
        "vector": vector_health(),
        "article_fetch": article_fetch_health(),
        "transcription": transcription_health(),
        "voice_archive": {"status": "unknown"},
        "graph": {"status": "unknown"},
        "jobs": {"status": "unknown"},
        "worker": worker_health(),
    }

    session = get_session()
    try:
        session.query(func.count(RawEntry.id)).filter(RawEntry.user_id == user_id).scalar()
        checks["db"] = {"status": "ok"}
        checks["jobs"] = job_backlog_health(session, user_id)
        from thoughtpins.memory.graph_backend import graph_backend_health
        from thoughtpins.voice_archive import voice_archive_health

        checks["graph"] = graph_backend_health(session)
        checks["voice_archive"] = voice_archive_health(session, user_id)
    except Exception as e:
        checks["db"] = {"status": "error", "detail": str(e)[:200]}
        checks["jobs"] = {"status": "error", "detail": str(e)[:200]}
    finally:
        session.close()

    checks["redis"] = redis_health()
    return checks


def build_readiness_checks() -> dict[str, Any]:
    """Check shared runtime dependencies without reading tenant-owned data."""
    checks: dict[str, Any] = {
        "db": {"status": "unknown"},
        "redis": redis_health(),
        "worker": worker_health(),
        "vector": vector_health(),
    }
    session = get_session()
    try:
        session.execute(text("SELECT 1")).scalar_one()
        checks["db"] = {"status": "ok"}
    except Exception as exc:
        checks["db"] = {"status": "error", "detail": str(exc)[:200]}
    finally:
        session.close()
    return checks


def deep_health_status(checks: dict[str, Any]) -> str:
    return "ok" if all(check.get("status") in HEALTHY_STATUSES for check in checks.values()) else "degraded"


def llm_health() -> dict[str, Any]:
    base = {
        "configured": bool(config.LLM_API_KEY),
        "endpoint_configured": bool(config.LLM_BASE_URL),
        "live_check": config.LLM_HEALTHCHECK_LIVE,
    }
    if not config.LLM_API_KEY:
        return {"status": "missing_api_key", **base}
    if not config.LLM_HEALTHCHECK_LIVE:
        return {"status": "configured", **base}

    try:
        from thoughtpins.llm.client import get_llm_client

        get_llm_client().chat(
            [{"role": "user", "content": "health"}],
            temperature=0.0,
            max_tokens=1,
        )
        return {"status": "ok", **base}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200], **base}


def vector_health() -> dict[str, Any]:
    details: dict[str, Any] = {
        "mode": config.VECTOR_MODE,
        "embedding_configured": config.EMBEDDING_PROVIDER != "openai" or bool(config.OPENAI_API_KEY),
        "live_check": config.VECTOR_HEALTHCHECK_LIVE,
    }
    try:
        from thoughtpins.library import document_indexing_backlog

        details["document_index_backlog"] = document_indexing_backlog()
    except Exception:
        details["document_index_backlog"] = "unknown"
    if config.EMBEDDING_PROVIDER == "openai":
        details["embedding_dimensions"] = config.OPENAI_EMBEDDING_DIMENSIONS
        if not config.OPENAI_API_KEY:
            return {"status": "missing_api_key", **details}
    elif config.EMBEDDING_PROVIDER not in {"llm", "local"}:
        return {"status": "error", "detail": "Unknown embedding provider", **details}

    if config.VECTOR_MODE == "qdrant_local":
        path = config.qdrant_path()
        parent = path.parent
        details["path"] = str(path)
        details["path_exists"] = path.exists()
        if not path.exists() and not (parent.exists() and os.access(parent, os.W_OK)):
            return {"status": "error", "detail": "Qdrant path parent is not writable", **details}
    elif config.VECTOR_MODE == "qdrant_remote":
        details["remote_configured"] = bool(config.QDRANT_URL)
        details["authentication_configured"] = bool(config.QDRANT_API_KEY)
        if not config.QDRANT_URL:
            return {"status": "error", "detail": "Qdrant endpoint is not configured", **details}
    elif config.VECTOR_MODE not in {"memory", "faiss", "chroma"}:
        return {"status": "error", "detail": "Unknown vector mode", **details}

    if not config.VECTOR_HEALTHCHECK_LIVE:
        return {"status": "configured", **details}

    try:
        from thoughtpins.memory.vector_store import get_vector_store

        count = get_vector_store().count()
        return {"status": "ok", "points": count, **details}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200], **details}


def job_backlog_health(session, user_id: str) -> dict[str, Any]:
    statuses = ["pending", "retry", "queued", "running", "failed", "dead_letter"]
    counts = {
        status: session.query(func.count(IngestionJob.id))
        .filter(IngestionJob.user_id == user_id, IngestionJob.status == status)
        .scalar()
        for status in statuses
    }
    return {"status": "ok", **counts}


def redis_health() -> dict[str, Any]:
    if not config.REDIS_URL:
        return {"status": "disabled"}
    try:
        from redis import Redis

        client = Redis.from_url(config.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return {"status": "ok", "required": redis_is_required()}
    except Exception as e:
        required = redis_is_required()
        return {
            "status": "error" if required else "warn",
            "required": required,
            "detail": str(e)[:200],
        }


def redis_is_required() -> bool:
    return config.is_production() or config.INGESTION_QUEUE_BACKEND == "celery" or config.RATE_LIMIT_ENABLED


def transcription_health() -> dict[str, Any]:
    """Report configuration readiness without exposing provider or model names."""

    if config.TRANSCRIPTION_PROVIDER == "hosted":
        configured = bool(config.TRANSCRIPTION_API_KEY and config.TRANSCRIPTION_BASE_URL and config.TRANSCRIPTION_MODEL)
        return {"status": "configured" if configured else "error", "processing": "external"}
    if config.TRANSCRIPTION_PROVIDER != "local":
        return {"status": "error", "detail": "Unknown transcription mode"}
    try:
        import importlib.util

        available = importlib.util.find_spec("whisper") is not None
    except (ImportError, ValueError):
        available = False
    return {"status": "configured" if available else "error", "processing": "local"}
