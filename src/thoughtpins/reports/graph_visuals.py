"""Graph visualization exports -- PyVis HTML, Mermaid snippets, GraphML."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from loguru import logger

from thoughtpins.config import config
from thoughtpins.memory.graph_store import GraphStore
from thoughtpins.store import get_session
from thoughtpins.utils import local_today


def export_all_graphs(days_back: int = 90, user_id: str | None = None) -> dict[str, Path]:
    """Export all graph formats to the vault _system directory."""
    session = get_session()
    try:
        gs = GraphStore(session, user_id=user_id)

        today = local_today()
        since = today - timedelta(days=days_back)
        G = gs.build_graph(since=since)

        out_dir = config.vault_path() / "_system" / "graph_exports"
        if user_id:
            out_dir = out_dir / user_id
        out_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        # GraphML
        try:
            results["graphml"] = gs.export_graphml(out_dir / "memory_graph.graphml", G)
        except Exception as e:
            logger.error("GraphML export failed: {}", e)

        # PyVis HTML
        try:
            results["html"] = gs.export_pyvis_html(out_dir / "memory_graph.html", G)
        except Exception as e:
            logger.error("PyVis export failed: {}", e)

        # CSV
        try:
            nodes_path, edges_path = gs.export_csv(out_dir, G)
            results["nodes_csv"] = nodes_path
            results["edges_csv"] = edges_path
        except Exception as e:
            logger.error("CSV export failed: {}", e)

        # Mermaid
        try:
            mermaid = gs.export_mermaid(G)
            mermaid_path = out_dir / "memory_graph.md"
            mermaid_path.write_text(f"```mermaid\n{mermaid}\n```\n", encoding="utf-8")
            results["mermaid"] = mermaid_path
        except Exception as e:
            logger.error("Mermaid export failed: {}", e)

        logger.info("Graph exports complete: {}", list(results.keys()))
        return results
    finally:
        session.close()
