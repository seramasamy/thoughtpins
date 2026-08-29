"""Reports, graph projections, and portable-vault export routes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from loguru import logger

from thoughtpins.api_contracts.common import INTERNAL_ERROR_MESSAGE
from thoughtpins.audit import record_audit_event
from thoughtpins.config import config
from thoughtpins.obsidian.exporter import ObsidianExporter
from thoughtpins.reports.generator import ReportGenerator
from thoughtpins.reports.graph_visuals import export_all_graphs
from thoughtpins.store import get_session


def create_exports_router(*, current_user_dependency: Callable[..., str]) -> APIRouter:
    router = APIRouter()

    @router.get("/report")
    @router.get("/v1/reports")
    async def report(
        type: str = Query("weekly", max_length=64, description="daily, weekly, monthly, person, place, or topic"),
        query: str = Query("", max_length=255, description="Name or topic for person/place/topic reports"),
        user_id: str = Depends(current_user_dependency),
    ) -> dict[str, Any]:
        session = get_session()
        try:
            generator = ReportGenerator(session, user_id=user_id)
            markdown = generator.generate_markdown(type, query or type)
            # Per-user directory, not the shared root: two users asking for
            # the same report type produced the same filename, and the second
            # write replaced the first user's file with the second user's
            # content. The response returns the markdown either way; the file
            # is a per-account convenience copy.
            reports_dir = config.reports_path() / user_id
            reports_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{type}_{query}" if query else type
            safe_name = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in safe_name)
            report_path = reports_dir / f"{safe_name[:180]}.md"
            report_path.write_text(markdown, encoding="utf-8")

            return {
                "report_type": type,
                "query": query,
                "markdown": markdown,
            }
        finally:
            session.close()

    @router.get("/graph")
    @router.get("/v1/graph")
    async def graph(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        try:
            results = export_all_graphs(user_id=user_id)
            return {
                "status": "ok",
                "formats": sorted(results),
            }
        except Exception as exc:
            logger.exception("Graph export failed")
            raise HTTPException(status_code=500, detail=INTERNAL_ERROR_MESSAGE) from exc

    @router.get("/graph/html")
    @router.get("/v1/graph/html")
    async def graph_html(user_id: str = Depends(current_user_dependency)) -> HTMLResponse:
        html_path = config.vault_path() / "_system" / "graph_exports" / user_id / "memory_graph.html"
        if not html_path.exists():
            results = export_all_graphs(user_id=user_id)
            html_path = Path(results.get("html", html_path))
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="Graph has not been generated")

    @router.post("/export")
    @router.post("/v1/export/obsidian")
    @router.post("/v1/export/vault")
    async def export_obsidian(
        package_zip: bool = Query(False, alias="zip"),
        obsidian_defaults: bool = Query(False),
        incremental: bool = Query(False, description="Preserve user-edited files in the server-side vault projection."),
        conflict_policy: Literal["preserve", "overwrite"] = Query("preserve"),
        user_id: str = Depends(current_user_dependency),
    ) -> dict[str, Any]:
        session = get_session()
        try:
            exporter = ObsidianExporter(session, user_id=user_id)
            stats = exporter.export_all(
                package_zip=package_zip,
                obsidian_defaults=obsidian_defaults,
                incremental=incremental,
                conflict_policy=conflict_policy,
            )
            validation = exporter.validation_result.as_dict() if exporter.validation_result else None
            return {
                "status": "ok" if not validation or validation.get("ok") else "validation_failed",
                "format": "obsidian_compatible_vault",
                "stats": {key: value for key, value in stats.items() if key != "zip_path"},
                "validation": validation,
            }
        finally:
            session.close()

    @router.get(
        "/v1/export/vault/download",
        response_class=FileResponse,
        summary="Download an Obsidian-compatible vault",
    )
    async def download_obsidian_vault(
        obsidian_defaults: bool = Query(True),
        user_id: str = Depends(current_user_dependency),
    ) -> FileResponse:
        session = get_session()
        try:
            exporter = ObsidianExporter(session, user_id=user_id)
            stats = exporter.export_all(package_zip=True, obsidian_defaults=obsidian_defaults)
            validation = exporter.validation_result
            if validation and not validation.ok:
                raise HTTPException(status_code=500, detail="Vault validation failed; download was not released")
            zip_path = Path(str(stats["zip_path"]))
            record_audit_event(
                session,
                user_id=user_id,
                action="vault.exported",
                metadata={"vault_files": stats.get("vault_files", 0), "obsidian_defaults": obsidian_defaults},
            )
            return FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=f"thought-pins-vault-{datetime.now(timezone.utc).date().isoformat()}.zip",
                headers={"Cache-Control": "private, no-store"},
            )
        finally:
            session.close()

    return router
