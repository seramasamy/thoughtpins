"""Pluggable graph-memory backends.

The relational Thought Pins database remains the source of truth. External graph
engines are auxiliary/shadow retrieval layers until evals prove they improve
recall without weakening tenant isolation or delete/export guarantees.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.memory.ontology import ontology_schema_fragment


@dataclass(frozen=True)
class GraphEpisode:
    user_id: str
    episode_id: str
    name: str
    body: str
    source: str = "text"
    source_description: str = ""
    reference_time: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSearchHit:
    text: str
    score: float = 0.0
    source: str = "internal_sql"
    entity_names: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphBackendStatus:
    provider: str
    status: str
    detail: str = ""
    shadow: bool = False


class GraphBackend(Protocol):
    provider: str

    def status(self) -> GraphBackendStatus: ...

    def add_episode(self, episode: GraphEpisode) -> bool: ...

    def search(self, query: str, *, user_id: str, limit: int = 10) -> list[GraphSearchHit]: ...

    def delete_user(self, user_id: str) -> bool: ...


class InternalSqlGraphBackend:
    provider = "internal_sql"

    def __init__(self, session: Session):
        self.session = session

    def status(self) -> GraphBackendStatus:
        return GraphBackendStatus(provider=self.provider, status="ok", detail="SQL entities/relationships")

    def add_episode(self, episode: GraphEpisode) -> bool:
        return True

    def search(self, query: str, *, user_id: str, limit: int = 10) -> list[GraphSearchHit]:
        from thoughtpins.memory.search import graph_search_hits

        return graph_search_hits(self.session, query, user_id=user_id, limit=limit)

    def delete_user(self, user_id: str) -> bool:
        # SQL graph rows are deleted by normal account deletion cascades.
        return True


class GraphitiBackend:
    provider = "graphiti"

    def __init__(self) -> None:
        self._graphiti: Any | None = None
        self._init_error = ""
        self._initialize()

    def _initialize(self) -> None:
        try:
            os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", str(config.GRAPHITI_TELEMETRY_ENABLED).lower())
            from graphiti_core import Graphiti

            driver = self._build_driver()
            if driver is not None:
                self._graphiti = Graphiti(graph_driver=driver)
            elif config.GRAPHITI_NEO4J_URI:
                self._graphiti = Graphiti(
                    config.GRAPHITI_NEO4J_URI,
                    config.GRAPHITI_NEO4J_USER,
                    config.GRAPHITI_NEO4J_PASSWORD,
                )
            else:
                self._init_error = "Graphiti installed, but no usable graph driver is configured"
        except ImportError as exc:
            self._init_error = f"graphiti-core is not installed: {exc}"
        except Exception as exc:
            self._init_error = str(exc)[:300]

    def _build_driver(self) -> Any | None:
        driver_name = config.GRAPHITI_DRIVER
        if driver_name == "kuzu":
            from graphiti_core.driver.kuzu_driver import KuzuDriver

            return KuzuDriver(db=str(config.resolve_path(config.GRAPHITI_KUZU_PATH)))
        if driver_name == "neo4j":
            if not config.GRAPHITI_NEO4J_URI:
                return None
            from graphiti_core.driver.neo4j_driver import Neo4jDriver

            return Neo4jDriver(
                uri=config.GRAPHITI_NEO4J_URI,
                user=config.GRAPHITI_NEO4J_USER,
                password=config.GRAPHITI_NEO4J_PASSWORD,
            )
        if driver_name == "falkordb":
            from graphiti_core.driver.falkordb_driver import FalkorDriver

            return FalkorDriver(
                host=config.GRAPHITI_FALKOR_HOST,
                port=config.GRAPHITI_FALKOR_PORT,
                username=config.GRAPHITI_FALKOR_USERNAME or None,
                password=config.GRAPHITI_FALKOR_PASSWORD or None,
                database=config.GRAPHITI_FALKOR_DATABASE,
            )
        self._init_error = f"Unsupported Graphiti driver: {driver_name}"
        return None

    def status(self) -> GraphBackendStatus:
        if self._graphiti is None:
            return GraphBackendStatus(provider=self.provider, status="disabled", detail=self._init_error)
        return GraphBackendStatus(provider=self.provider, status="configured", detail=config.GRAPHITI_DRIVER)

    def add_episode(self, episode: GraphEpisode) -> bool:
        graphiti = self._graphiti
        if graphiti is None:
            return False

        async def _add() -> None:
            from graphiti_core.nodes import EpisodeType

            source = {
                "message": EpisodeType.message,
                "json": EpisodeType.json,
            }.get(episode.source, EpisodeType.text)
            await graphiti.add_episode(
                name=episode.name,
                episode_body=episode.body,
                source=source,
                source_description=episode.source_description or "Thought Pins memory episode",
                reference_time=episode.reference_time or datetime.now(timezone.utc),
                group_id=episode.user_id,
                uuid=episode.episode_id,
            )

        return _run_async_safely(_add, "Graphiti add_episode")

    def search(self, query: str, *, user_id: str, limit: int = 10) -> list[GraphSearchHit]:
        graphiti = self._graphiti
        if graphiti is None:
            return []

        async def _search():
            return await graphiti.search(query, group_ids=[user_id], num_results=limit)

        try:
            results = _run_async_value(_search)
        except Exception as exc:
            logger.warning("Graphiti search failed: {}", str(exc)[:200])
            return []
        hits: list[GraphSearchHit] = []
        for result in results or []:
            text = str(getattr(result, "fact", "") or getattr(result, "name", "") or result)
            hits.append(
                GraphSearchHit(text=text, score=float(getattr(result, "score", 0.75) or 0.75), source="graphiti")
            )
        return hits[:limit]

    def delete_user(self, user_id: str) -> bool:
        # Graphiti delete APIs vary by backend/version. Keep this false so data
        # lifecycle remains SQL-authoritative until the exact backend is tested.
        return False


class ShadowGraphBackend:
    provider = "shadow"

    def __init__(self, primary: GraphBackend, shadow: GraphBackend):
        self.primary = primary
        self.shadow = shadow

    def status(self) -> GraphBackendStatus:
        primary = self.primary.status()
        shadow = self.shadow.status()
        return GraphBackendStatus(
            provider=primary.provider,
            status=primary.status,
            detail=f"shadow={shadow.provider}:{shadow.status}:{shadow.detail}",
            shadow=True,
        )

    def add_episode(self, episode: GraphEpisode) -> bool:
        ok = self.primary.add_episode(episode)
        try:
            self.shadow.add_episode(episode)
        except Exception as exc:
            logger.warning("Shadow graph add failed: {}", str(exc)[:200])
        return ok

    def search(self, query: str, *, user_id: str, limit: int = 10) -> list[GraphSearchHit]:
        primary_hits = self.primary.search(query, user_id=user_id, limit=limit)
        try:
            shadow_hits = self.shadow.search(query, user_id=user_id, limit=max(1, limit // 2))
        except Exception as exc:
            logger.warning("Shadow graph search failed: {}", str(exc)[:200])
            shadow_hits = []
        return (primary_hits + shadow_hits)[:limit]

    def delete_user(self, user_id: str) -> bool:
        ok = self.primary.delete_user(user_id)
        try:
            self.shadow.delete_user(user_id)
        except Exception as exc:
            logger.warning("Shadow graph delete failed: {}", str(exc)[:200])
        return ok


def get_graph_backend(session: Session) -> GraphBackend:
    primary: GraphBackend
    if config.GRAPH_PROVIDER == "graphiti":
        primary = GraphitiBackend()
        if primary.status().status == "disabled":
            primary = InternalSqlGraphBackend(session)
    else:
        primary = InternalSqlGraphBackend(session)

    if config.GRAPH_SHADOW_ENABLED and config.GRAPH_PROVIDER != "graphiti":
        return ShadowGraphBackend(primary, GraphitiBackend())
    return primary


def graph_backend_health(session: Session | None = None) -> dict[str, object]:
    if session is None:
        return {
            "provider": config.GRAPH_PROVIDER,
            "shadow_enabled": config.GRAPH_SHADOW_ENABLED,
            "status": "not_checked",
        }
    status = get_graph_backend(session).status()
    return {
        "provider": status.provider,
        "status": status.status,
        "detail": status.detail,
        "shadow": status.shadow,
        "configured_provider": config.GRAPH_PROVIDER,
        "shadow_enabled": config.GRAPH_SHADOW_ENABLED,
        "ontology": ontology_schema_fragment(),
    }


def add_episode_to_graph_backend(session: Session, episode: GraphEpisode) -> bool:
    try:
        return get_graph_backend(session).add_episode(episode)
    except Exception as exc:
        logger.warning("Graph backend episode add failed: {}", str(exc)[:200])
        return False


def _run_async_safely(factory, label: str) -> bool:
    try:
        _run_async_value(factory)
        return True
    except RuntimeError as exc:
        logger.warning("{} skipped inside existing event loop: {}", label, exc)
        return False
    except Exception as exc:
        logger.warning("{} failed: {}", label, str(exc)[:200])
        return False


def _run_async_value(factory):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    raise RuntimeError("async graph backend call cannot be run synchronously inside an active event loop")
