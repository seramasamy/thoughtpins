"""Optional, rights-aware source connectors for Thought Pins."""

from thoughtpins_sources.open_access import OpenAccessCandidate, extract_doi, resolve_open_access

__all__ = ["OpenAccessCandidate", "extract_doi", "resolve_open_access"]
