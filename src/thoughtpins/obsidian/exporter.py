"""Compatibility adapter for the first-class Thought Pins vault exporter."""

from __future__ import annotations

from thoughtpins.vault.exporter import VaultExporter


class ObsidianExporter(VaultExporter):
    """Backward-compatible name for existing API, Telegram, and ingestion code."""


__all__ = ["ObsidianExporter", "VaultExporter"]
