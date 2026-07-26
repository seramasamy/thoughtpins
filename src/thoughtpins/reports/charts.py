"""Chart generation using matplotlib only (no seaborn)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from thoughtpins.db import Entity, Event, Memory
from thoughtpins.store import get_session
from thoughtpins.utils import local_today


def plot_interactions_by_person(
    output_path: str | Path,
    session: Session | None = None,
    top_n: int = 15,
) -> Path:
    """Bar chart: number of memories/interactions per person."""
    if session is None:
        session = get_session()

    # Count memories per subject entity (people)
    results = (
        session.query(
            Entity.canonical_name,
            func.count(Memory.id).label("cnt"),
        )
        .join(Memory, Memory.subject_entity_id == Entity.id)
        .filter(Entity.type == "person", Entity.canonical_name != "User")
        .group_by(Entity.id)
        .order_by(func.count(Memory.id).desc())
        .limit(top_n)
        .all()
    )

    if not results:
        logger.warning("No data for interactions chart")
        return Path(output_path)

    names = [r[0] for r in results]
    counts = [r[1] for r in results]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(range(len(names)), counts, color="#4a9eff")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Memories / Interactions")
    ax.set_title("Interactions by Person")
    ax.set_xlabel("Person")
    fig.tight_layout()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved interactions chart: {}", path)
    return path


def plot_event_timeline(
    output_path: str | Path,
    session: Session | None = None,
    days_back: int = 90,
) -> Path:
    """Timeline chart of events over time."""
    if session is None:
        session = get_session()

    today = local_today()
    since = today - timedelta(days=days_back)

    results = (
        session.query(Event.local_date, func.count(Event.id))
        .filter(Event.local_date >= since)
        .group_by(Event.local_date)
        .order_by(Event.local_date)
        .all()
    )

    if not results:
        logger.warning("No event data for timeline chart")
        return Path(output_path)

    dates = [r[0] for r in results]
    counts = [r[1] for r in results]

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.fill_between(range(len(dates)), counts, alpha=0.3, color="#4a9eff")
    ax.plot(range(len(dates)), counts, color="#4a9eff", linewidth=2)
    # Label every nth date
    step = max(1, len(dates) // 10)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([str(d) for d in dates[::step]], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Events per Day")
    ax.set_title(f"Event Timeline (last {days_back} days)")
    fig.tight_layout()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved timeline chart: {}", path)
    return path


def plot_memory_types_pie(
    output_path: str | Path,
    session: Session | None = None,
) -> Path:
    """Pie chart of memory type distribution."""
    if session is None:
        session = get_session()

    results = (
        session.query(Memory.memory_type, func.count(Memory.id))
        .group_by(Memory.memory_type)
        .all()
    )

    if not results:
        return Path(output_path)

    labels = [r[0] for r in results]
    sizes = [r[1] for r in results]
    colors = plt.cm.Set3(range(len(labels)))

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90)
    ax.set_title("Memory Type Distribution")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved memory types pie: {}", path)
    return path
