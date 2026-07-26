"""Static web app server used by the local production rehearsal.

The API can serve `/app` directly, but the closed-beta rehearsal also runs a
separate web surface. This module serves the built frontend and proxies `/v1`
to the API service so browser behavior stays same-origin.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from thoughtpins.config import config
from thoughtpins.logging_config import setup_logging

API_UPSTREAM = os.getenv("THOUGHTPINS_WEB_API_UPSTREAM", "http://127.0.0.1:8420").rstrip("/")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

app = FastAPI(title="Thought Pins Web", version=config.API_VERSION, docs_url=None, redoc_url=None)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "Thought Pins Web", "api_upstream": API_UPSTREAM}


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/app", status_code=302)


@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
@app.get("/app/{path:path}", include_in_schema=False)
async def web_app(path: str = "") -> Response:
    frontend_dir = _resolve_frontend_dir()
    file_path = _safe_frontend_file(frontend_dir, path)
    if file_path is None:
        asset_like = "." in Path(path).name
        file_path = None if asset_like else _safe_frontend_file(frontend_dir, "")
    if file_path is None:
        return JSONResponse({"error": {"code": "asset_not_found", "message": "Web asset not found."}}, status_code=404)
    return FileResponse(file_path)


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
async def proxy_api(path: str, request: Request) -> Response:
    upstream = httpx.URL(f"{API_UPSTREAM}/v1/{path}", query=request.url.query.encode("utf-8"))
    headers = _forward_headers(request.headers.items())
    body = await request.body()
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=False) as client:
        proxied = await client.request(request.method, upstream, headers=headers, content=body)
    return Response(
        content=proxied.content,
        status_code=proxied.status_code,
        headers=dict(_response_headers(proxied.headers.items())),
        media_type=proxied.headers.get("content-type"),
    )


def _resolve_frontend_dir() -> Path:
    candidates = [
        config.resolve_path(Path("frontend") / "dist"),
        (Path.cwd() / "frontend" / "dist").resolve(),
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        config.resolve_path(Path("frontend") / "static"),
        (Path.cwd() / "frontend" / "static").resolve(),
        Path(__file__).resolve().parents[2] / "frontend" / "static",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[0]


def _safe_frontend_file(frontend_dir: Path, path: str) -> Path | None:
    candidate = frontend_dir / ("index.html" if not path else path)
    try:
        resolved = candidate.resolve()
        resolved.relative_to(frontend_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _forward_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {key: value for key, value in headers if key.lower() not in HOP_BY_HOP_HEADERS}


def _response_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    blocked = HOP_BY_HOP_HEADERS | {"content-encoding"}
    return {key: value for key, value in headers if key.lower() not in blocked}


def main() -> None:
    setup_logging()
    host = os.getenv("THOUGHTPINS_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("THOUGHTPINS_WEB_PORT", "8421"))
    uvicorn.run("thoughtpins.web_proxy:app", host=host, port=port, log_level=config.LOG_LEVEL.lower(), reload=False)


if __name__ == "__main__":
    main()
