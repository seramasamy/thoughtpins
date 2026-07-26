"""Report generator -- produces Markdown, HTML, and PDF reports from memory data."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import Entity, Memory, Relationship, Report
from thoughtpins.memory.graph_store import GraphStore
from thoughtpins.memory.search import search
from thoughtpins.memory.store import MemoryStore
from thoughtpins.store import get_session
from thoughtpins.utils import local_today


class ReportGenerator:
    """Generate reports from the memory database."""

    def __init__(self, session: Session | None = None, user_id: str | None = None):
        self._session = session or get_session()
        self.user_id = user_id
        self._store = MemoryStore(self._session, user_id=user_id)
        self._graph_store = GraphStore(self._session, user_id=user_id)
        self._reports_dir = config.reports_path()

    def generate_markdown(self, query_type: str, query_text: str = "", **kwargs) -> str:
        """Generate a Markdown report based on query type."""
        if query_type == "person":
            return self._report_person(query_text)
        elif query_type == "place":
            return self._report_place(query_text)
        elif query_type == "weekly":
            return self._report_weekly()
        elif query_type == "daily":
            return self._report_daily()
        elif query_type == "monthly":
            return self._report_monthly()
        elif query_type == "topic":
            return self._report_topic(query_text)
        elif query_type == "network":
            return self._report_network(kwargs.get("days", 30))
        else:
            return self._report_general(query_text)

    def _report_person(self, name: str) -> str:
        entity = self._store.get_entity_by_name(name, "person")
        if not entity:
            entity = self._store.get_entity_by_name(name)
        if not entity:
            return f"No records found for '{name}'."

        memories = self._store.get_memories_by_entity(entity.id)
        relationships = self._store.get_relationships_for_entity(entity.id)
        attrs = entity.attributes_json or []

        lines = [
            f"# Person Report: {entity.canonical_name}",
            "",
            f"**Entity ID:** {entity.id}",
            f"**Type:** {entity.type}",
            f"**First seen:** {entity.created_at_utc}",
            f"**Last updated:** {entity.updated_at_utc}",
            f"**Sensitivity:** {entity.sensitivity}",
            "",
            "## Attributes",
        ]
        for a in attrs:
            lines.append(f"- **{a['key']}**: {a['value']} (confidence: {a.get('confidence', 'unknown')})")
        if not attrs:
            lines.append("- No attributes recorded.")

        lines.extend(["", "## Recent Memories"])
        for m in memories[:20]:
            sens = f" [{m.sensitivity}]" if m.sensitivity not in ("personal",) else ""
            lines.append(f"- [{m.local_date}] {m.text} (confidence: {m.confidence}){sens}")
            lines.append(f"  - Source: `raw_entry:{m.raw_entry_id}` memory:`{m.id}`")

        lines.extend(["", "## Relationships"])
        for r in relationships[:20]:
            other_ent = self._get_other_entity(r, entity.id)
            other_name = other_ent.canonical_name if other_ent else "unknown"
            lines.append(f"- **{r.relation_type}** -> [[{other_name}]] (weight: {r.weight}, confidence: {r.confidence})")
        if not relationships:
            lines.append("- No relationships recorded.")

        lines.extend(["", "## Memory Links Used"])
        for m in memories[:20]:
            lines.append(f"- memory:`{m.id}` -> `{m.text[:80]}...`")

        return "\n".join(lines)

    def _report_place(self, name: str) -> str:
        entity = self._store.get_entity_by_name(name, "place")
        if not entity:
            return f"No place found for '{name}'."

        events = self._store.get_events_by_place(name, limit=20)

        lines = [
            f"# Place Report: {entity.canonical_name}",
            "",
            f"**Total visits recorded:** {len(events)}",
            "",
            "## Visits",
        ]
        for evt in events:
            participants = self._store.get_event_participants(evt.id)
            pnames = [p[0].canonical_name for p in participants]
            lines.append(f"### {evt.local_date} -- {evt.name}")
            lines.append(f"- **With:** {', '.join(pnames) if pnames else 'unknown'}")
            lines.append(f"- **Summary:** {evt.summary or 'No summary'}")
            lines.append(f"- **Source:** event:`{evt.id}` entry:`{evt.source_raw_entry_id}`")
            lines.append("")

        lines.extend(["", "## Source Memory Links"])
        for evt in events:
            lines.append(f"- event:`{evt.id}` [[{evt.name}]]")

        return "\n".join(lines)

    def _report_weekly(self) -> str:
        today = local_today()
        start = today - timedelta(days=today.weekday())
        return self._report_date_range(start, today, "Weekly Report")

    def _report_daily(self) -> str:
        today = local_today()
        return self._report_date_range(today, today, "Daily Recap")

    def _report_monthly(self) -> str:
        today = local_today()
        start = today.replace(day=1)
        return self._report_date_range(start, today, "Monthly Report")

    def _report_date_range(self, start: date, end: date, title: str) -> str:
        events = self._store.get_events_by_date_range(start, end)
        entries = self._store.get_entries_by_date_range(start, end)
        memories_q = self._session.query(Memory).filter(
            Memory.local_date >= start,
            Memory.local_date <= end,
        )
        if self.user_id:
            memories_q = memories_q.filter(Memory.user_id == self.user_id)
        memories = memories_q.order_by(Memory.local_date.desc()).all()
        entries = sorted(
            entries,
            key=lambda entry: (entry.user_importance or 0, entry.created_at_utc),
            reverse=True,
        )
        events = sorted(
            events,
            key=lambda event: (
                event.raw_entry.user_importance if event.raw_entry and event.raw_entry.user_importance else 0,
                event.local_date or date.min,
            ),
            reverse=True,
        )
        memories = sorted(
            memories,
            key=lambda memory: (
                memory.raw_entry.user_importance if memory.raw_entry and memory.raw_entry.user_importance else 0,
                memory.local_date or date.min,
                memory.created_at_utc,
            ),
            reverse=True,
        )
        rated_entries = [entry for entry in entries if entry.user_importance is not None]

        lines = [
            f"# {title}: {start.isoformat()} to {end.isoformat()}",
            "",
            f"**Entries:** {len(entries)}",
            f"**Events:** {len(events)}",
            f"**Memories extracted:** {len(memories)}",
            f"**Rated entries:** {len(rated_entries)}",
            "",
            "## Events",
        ]
        for evt in events:
            participants = self._store.get_event_participants(evt.id)
            pnames = [p[0].canonical_name for p in participants]
            lines.append(f"- **{evt.local_date}** -- {evt.name} (with {', '.join(pnames) if pnames else 'others'})")
            if evt.summary:
                lines.append(f"  {evt.summary[:200]}")

        lines.extend(["", "## People Mentioned"])
        people_ids = set()
        for m in memories:
            if m.subject_entity_id:
                people_ids.add(m.subject_entity_id)
            if m.object_entity_id:
                people_ids.add(m.object_entity_id)
        for pid in list(people_ids)[:30]:
            ent_q = self._session.query(Entity).filter(Entity.id == pid)
            if self.user_id:
                ent_q = ent_q.filter(Entity.user_id == self.user_id)
            ent = ent_q.first()
            if ent and ent.type == "person":
                lines.append(f"- [[{ent.canonical_name}]]")

        lines.extend(["", "## Notable Memories"])
        for m in memories[:30]:
            sens = f" [{m.sensitivity}]" if m.sensitivity not in ("personal",) else ""
            rating = (
                f" [importance: {m.raw_entry.user_importance}/5]"
                if m.raw_entry and m.raw_entry.user_importance is not None
                else ""
            )
            lines.append(f"- [{m.local_date}] [{m.memory_type}]{rating} {m.text}{sens}")
            lines.append(f"  - memory:`{m.id}` entry:`{m.raw_entry_id}`")

        lines.extend(["", "## Sensitivity Warnings"])
        sens_tags = set(m.sensitivity for m in memories if m.sensitivity not in ("personal", "public_ok"))
        if sens_tags:
            for s in sorted(sens_tags):
                lines.append(f"- Contains **{s}** information")
        else:
            lines.append("- No sensitivity warnings for this period.")

        return "\n".join(lines)

    def _report_topic(self, topic: str) -> str:
        results = search(topic, session=self._session, user_id=self.user_id, limit=30)
        lines = [
            f"# Topic Report: {topic}",
            "",
            f"**Results found:** {len(results)}",
            "",
        ]
        for r in results:
            lines.append(f"- [{r.local_date}] [{r.memory_type}] {r.text}")
            lines.append(f"  - Confidence: {r.confidence} | Sensitivity: {r.sensitivity}")
            lines.append(f"  - memory:`{r.memory_id}` entry:`{r.source_entry_id}`")

        return "\n".join(lines)

    def _report_network(self, days: int = 30) -> str:
        today = local_today()
        since = today - timedelta(days=days)
        G = self._graph_store.build_graph(since=since)

        lines = [
            f"# Network Report (last {days} days)",
            "",
            f"**Nodes:** {G.number_of_nodes()}",
            f"**Edges:** {G.number_of_edges()}",
            "",
            "## Top Connected People",
        ]
        # Degree centrality
        degree = sorted(G.degree(weight="weight"), key=lambda x: x[1], reverse=True)
        for nid, deg in degree[:15]:
            label = G.nodes[nid].get("label", nid)
            lines.append(f"- **{label}** (degree: {deg:.1f})")

        lines.extend(["", "## Mermaid Graph"])
        mermaid = self._graph_store.export_mermaid(G, max_nodes=30)
        lines.append("```mermaid")
        lines.append(mermaid)
        lines.append("```")

        return "\n".join(lines)

    def _report_general(self, query: str) -> str:
        results = search(query, session=self._session, user_id=self.user_id, limit=20)
        lines = [
            f"# Report: {query}",
            "",
            f"**Results found:** {len(results)}",
            "",
        ]
        for r in results:
            lines.append(f"- [{r.local_date}] [{r.memory_type}] {r.text}")
            lines.append(f"  - memory:`{r.memory_id}` entry:`{r.source_entry_id}`")

        if not results:
            lines.append("No results found. Try a different query or add more journal entries.")

        return "\n".join(lines)

    def generate_pdf(self, markdown_content: str, output_path: str | Path) -> Optional[Path]:
        """Try to generate PDF from Markdown. Returns path or None."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Always save the markdown
        md_path = path.with_suffix(".md")
        md_path.write_text(markdown_content, encoding="utf-8")

        # Try WeasyPrint
        try:
            from weasyprint import HTML
            html_content = f"<html><body><pre>{markdown_content}</pre></body></html>"
            HTML(string=html_content).write_pdf(str(path))
            logger.info("PDF generated via WeasyPrint: {}", path)
            return path
        except ImportError:
            logger.info("WeasyPrint not installed -- skipping PDF")
        except Exception as e:
            logger.warning("WeasyPrint PDF failed: {}", e)

        # Try ReportLab fallback
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate
            doc = SimpleDocTemplate(str(path), pagesize=letter)
            styles = getSampleStyleSheet()
            story = [Paragraph(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles["Normal"])
                     for line in markdown_content.split("\n") if line.strip()]
            doc.build(story)
            logger.info("PDF generated via ReportLab: {}", path)
            return path
        except ImportError:
            logger.info("ReportLab not installed -- PDF unavailable")
        except Exception as e:
            logger.warning("ReportLab PDF failed: {}", e)

        logger.info("PDF generation unavailable. Markdown saved at: {}", md_path)
        return None

    def save_report_to_db(self, query: str, report_type: str, md_path: str,
                          pdf_path: str | None = None, html_path: str | None = None,
                          memory_ids: list[str] | None = None,
                          entry_ids: list[str] | None = None) -> Report:
        report = Report(
            user_id=self.user_id,
            query=query,
            report_type=report_type,
            output_markdown_path=md_path,
            output_pdf_path=pdf_path,
            output_html_path=html_path,
            source_memory_ids_json=memory_ids or [],
            source_raw_entry_ids_json=entry_ids or [],
        )
        self._session.add(report)
        self._session.commit()
        return report

    def _get_other_entity(self, rel: Relationship, entity_id: str) -> Optional[Entity]:
        if rel.source_entity_id == entity_id:
            return rel.target_entity
        return rel.source_entity
