"""Optional disk projection for synchronous local journal processing."""

from __future__ import annotations

import time
from threading import Lock

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config

_EXPORT_LOCK = Lock()
_last_export_time = 0.0


def maybe_export_vault(session: Session, user_id: str, entry_id: str) -> None:
    # The hosted API cannot erase a different worker's filesystem on account
    # deletion. Exporting here would also decrypt every uploaded original into
    # that worker's vault. Hosted/asynchronous ingestion keeps the shared stores
    # authoritative; users can still explicitly download their vault via API.
    if config.is_production() or config.PROCESS_ENTRIES_ASYNC:
        return
    global _last_export_time
    now = time.time()
    with _EXPORT_LOCK:
        if now - _last_export_time <= 600:
            return
        try:
            from thoughtpins.obsidian.exporter import ObsidianExporter

            ObsidianExporter(session, user_id=user_id).export_all()
            _last_export_time = now
            logger.debug("Auto-exported local Obsidian vault after entry {}", entry_id)
        except Exception as exc:
            logger.warning("Auto-export failed (non-critical): {}", type(exc).__name__)
