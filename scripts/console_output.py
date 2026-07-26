"""Console output helpers for cross-platform evaluation scripts."""

from __future__ import annotations

import sys


def force_utf8_stdio() -> None:
    """Prefer UTF-8 output when a script prints model-generated text."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
