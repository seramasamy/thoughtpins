"""GraphStore -- NetworkX graph assembly and export from relational data."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import networkx as nx
from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.db import Entity, Event, EventParticipant, Relationship
from thoughtpins.store import get_session


class GraphStore:
    """Build and export graph representations of the memory network."""

    def __init__(self, session: Session | None = None, user_id: str | None = None):
        self._session = session or get_session()
        self.user_id = user_id

    def build_graph(
        self,
        since: date | None = None,
        entity_types: list[str] | None = None,
    ) -> nx.Graph:
        """Build a NetworkX graph from entities and relationships."""
        G = nx.Graph()

        # -- Nodes --
        q = self._session.query(Entity)
        if self.user_id:
            q = q.filter(Entity.user_id == self.user_id)
        if entity_types:
            q = q.filter(Entity.type.in_(entity_types))
        entities = q.all()

        for ent in entities:
            G.add_node(
                ent.id,
                label=ent.canonical_name,
                type=ent.type,
                sensitivity=ent.sensitivity,
            )

        # -- Edges from relationships table --
        rel_q = self._session.query(Relationship)
        if self.user_id:
            rel_q = rel_q.filter(Relationship.user_id == self.user_id)
        if since:
            rel_q = rel_q.filter(Relationship.last_seen_at >= since)
        relationships = rel_q.all()

        for rel in relationships:
            if G.has_node(rel.source_entity_id) and G.has_node(rel.target_entity_id):
                G.add_edge(
                    rel.source_entity_id,
                    rel.target_entity_id,
                    type=rel.relation_type,
                    weight=rel.weight,
                    confidence=rel.confidence,
                    sensitivity=rel.sensitivity,
                    evidence_count=rel.evidence_count,
                )

        # -- Edges from event participation --
        events_q = self._session.query(Event)
        if self.user_id:
            events_q = events_q.filter(Event.user_id == self.user_id)
        if since:
            events_q = events_q.filter(Event.local_date >= since)
        events = events_q.all()

        for event in events:
            participants = (
                self._session.query(EventParticipant)
                .filter(EventParticipant.user_id == self.user_id if self.user_id else True)
                .filter(EventParticipant.event_id == event.id)
                .all()
            )
            entity_ids = [p.entity_id for p in participants if G.has_node(p.entity_id)]
            for i, eid1 in enumerate(entity_ids):
                for eid2 in entity_ids[i + 1 :]:
                    if G.has_edge(eid1, eid2):
                        G[eid1][eid2]["weight"] = G[eid1][eid2].get("weight", 1.0) + 2.0
                    else:
                        G.add_edge(
                            eid1,
                            eid2,
                            type="met_at",
                            weight=2.0,
                            confidence="observed_by_user",
                            sensitivity="personal",
                            evidence_count=1,
                        )

        logger.info("Built graph: {} nodes, {} edges", G.number_of_nodes(), G.number_of_edges())
        return G

    def export_graphml(self, output_path: str | Path, G: nx.Graph | None = None) -> Path:
        if G is None:
            G = self.build_graph()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(G, str(path))
        logger.info("Exported GraphML to {}", path)
        return path

    def export_csv(self, output_dir: str | Path, G: nx.Graph | None = None) -> tuple[Path, Path]:
        if G is None:
            G = self.build_graph()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        nodes_path = out / "nodes.csv"
        with open(nodes_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "label", "type", "sensitivity"])
            for nid, data in G.nodes(data=True):
                writer.writerow([nid, data.get("label", ""), data.get("type", ""), data.get("sensitivity", "")])

        edges_path = out / "edges.csv"
        with open(edges_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target", "type", "weight", "confidence", "evidence_count"])
            for u, v, data in G.edges(data=True):
                writer.writerow(
                    [
                        u,
                        v,
                        data.get("type", ""),
                        data.get("weight", 1.0),
                        data.get("confidence", ""),
                        data.get("evidence_count", 1),
                    ]
                )

        logger.info("Exported CSV: {} and {}", nodes_path, edges_path)
        return nodes_path, edges_path

    def export_pyvis_html(self, output_path: str | Path, G: nx.Graph | None = None) -> Path:
        try:
            from pyvis.network import Network
        except ImportError:
            logger.error("pyvis not installed")
            raise

        if G is None:
            G = self.build_graph()

        # Compute metrics
        degree_centrality = nx.degree_centrality(G)
        max_deg = max(degree_centrality.values()) if degree_centrality else 1.0

        net = Network(height="750px", width="100%", bgcolor="#1a1a2e", font_color="#e0e0e0")
        net.set_options("""
        var options = {
          "nodes": {
            "shape": "dot",
            "font": { "size": 14, "face": "sans-serif", "color": "#ffffff" }
          },
          "edges": {
            "smooth": { "type": "continuous", "roundness": 0.3 },
            "color": { "color": "#555577", "highlight": "#8888ff" },
            "width": 0.8
          },
          "physics": {
            "forceAtlas2Based": {
              "gravitationalConstant": -50,
              "centralGravity": 0.01,
              "springLength": 100,
              "springConstant": 0.08
            },
            "minVelocity": 0.75,
            "solver": "forceAtlas2Based"
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          }
        }
        """)

        color_map = {
            "person": "#4a9eff",
            "place": "#ff6b6b",
            "organization": "#ffd93d",
            "project": "#6bcb77",
            "topic": "#9b59b6",
            "event": "#e67e22",
        }

        # Add nodes with size proportional to degree, labels on important ones
        for nid, data in G.nodes(data=True):
            node_type = data.get("type", "concept")
            color = color_map.get(node_type, "#95a5a6")
            label = data.get("label", nid)
            deg = degree_centrality.get(nid, 0)
            # Scale: min 8, max 40 based on degree centrality
            size = 8 + int(32 * (deg / max_deg)) if max_deg > 0 else 12

            # Show label for top 15 nodes or high-degree nodes
            show_label = deg > 0.05 or len(label) < 15

            net.add_node(
                nid,
                label=label if show_label else "",
                title=f"<b>{label}</b><br>Type: {node_type}<br>Connections: {G.degree(nid)}<br>Centrality: {deg:.3f}",
                color=color,
                size=size,
                font={"size": max(10, int(10 + deg * 20)), "color": "#ffffff"},
            )

        # Add edges with labels for important relationships
        for u, v, data in G.edges(data=True):
            edge_type = data.get("type", "")
            weight = data.get("weight", 1.0)
            net.add_edge(
                u,
                v,
                title=f"{edge_type} (weight: {weight:.1f})",
                value=weight,
                label=edge_type if weight >= 3 else "",
            )

        # Build summary HTML panel
        summary_html = self._build_summary_html(G)

        # Save base HTML
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        net.save_graph(str(path))

        # Inject summary panel into the HTML
        raw_html = path.read_text(encoding="utf-8")
        raw_html = raw_html.replace(
            "</body>",
            summary_html + "\n</body>",
        )
        path.write_text(raw_html, encoding="utf-8")

        logger.info("Exported PyVis HTML with summary to {}", path)
        return path

    def _build_summary_html(self, G: nx.Graph) -> str:
        """Build an HTML summary panel for the graph export."""
        nodes_by_type: dict[str, list[str]] = {}
        for nid, data in G.nodes(data=True):
            nt = data.get("type", "concept")
            nodes_by_type.setdefault(str(nt), []).append(str(data.get("label", nid)))

        degree = sorted(G.degree(weight="weight"), key=lambda x: x[1], reverse=True)

        type_colors = {
            "person": "#4a9eff",
            "place": "#ff6b6b",
            "organization": "#ffd93d",
            "project": "#6bcb77",
            "topic": "#9b59b6",
            "event": "#e67e22",
        }

        # Top connected nodes
        top_nodes_html = ""
        for nid, deg in degree[:8]:
            label = G.nodes[nid].get("label", nid)
            nt = G.nodes[nid].get("type", "concept")
            color = type_colors.get(nt, "#95a5a6")
            top_nodes_html += (
                f'<div style="display:flex;align-items:center;margin:4px 0;">'
                f'<span style="background:{color};width:12px;height:12px;border-radius:50%;'
                f'display:inline-block;margin-right:8px;"></span>'
                f'<span style="flex:1;">{label}</span>'
                f'<span style="color:#888;">{deg} links</span></div>'
            )

        # Type counts
        type_html = ""
        for nt, items in sorted(nodes_by_type.items()):
            type_html += (
                f'<span style="background:{type_colors.get(nt, "#555")};color:#fff;'
                f"padding:2px 8px;border-radius:10px;margin:2px;display:inline-block;"
                f'font-size:11px;">{nt}: {len(items)}</span> '
            )

        return f"""
<div id="summary-panel" style="
    position:fixed;top:10px;right:10px;background:rgba(20,20,40,0.92);
    color:#e0e0e0;padding:16px;border-radius:10px;
    font-family:sans-serif;font-size:13px;max-width:280px;
    z-index:1000;border:1px solid #333;max-height:90vh;overflow-y:auto;
">
    <h3 style="margin:0 0 8px 0;color:#fff;">Memory Graph</h3>
    <p style="color:#888;margin:0 0 10px 0;font-size:11px;">
        {G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges
    </p>

    <div style="margin-bottom:12px;">
        <div style="font-weight:bold;margin-bottom:4px;color:#ccc;">Node Types</div>
        {type_html}
    </div>

    <div>
        <div style="font-weight:bold;margin-bottom:4px;color:#ccc;">Most Connected</div>
        {top_nodes_html}
    </div>

    <div style="margin-top:12px;font-size:10px;color:#666;">
        Drag to move &middot; Scroll to zoom &middot; Click for details
    </div>
</div>
"""

    def export_mermaid(self, G: nx.Graph | None = None, max_nodes: int = 50) -> str:
        if G is None:
            G = self.build_graph()

        lines = ["graph TD"]
        nodes_added: set[object] = set()

        for u, v, data in G.edges(data=True):
            if len(nodes_added) >= max_nodes:
                break
            u_label = G.nodes[u].get("label", u)[:30]
            v_label = G.nodes[v].get("label", v)[:30]
            u_safe = _safe_id(u_label)
            v_safe = _safe_id(v_label)
            nodes_added.add(u)
            nodes_added.add(v)
            edge_type = data.get("type", "")
            lines.append(f'    {u_safe}["{u_label}"] -->|{edge_type}| {v_safe}["{v_label}"]')

        return "\n".join(lines)


def _safe_id(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:32]
