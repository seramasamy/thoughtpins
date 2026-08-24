"""Public legal pages and backend-served web app routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from thoughtpins.config import config

_FRONTEND_BUILD_MARKER = ".thoughtpins-build.json"


def create_public_router() -> APIRouter:
    router = APIRouter()
    frontend_dir = _resolve_frontend_dir()
    frontend_index = frontend_dir / "index.html"
    site_dir = _resolve_site_dir()

    def safe_frontend_file(path: str) -> Path | None:
        candidate = frontend_index if not path else (frontend_dir / path)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(frontend_dir)
        except ValueError:
            return None
        return resolved if resolved.is_file() else None

    def safe_site_file(path: str | Path) -> Path | None:
        candidate = site_dir / path
        try:
            resolved = candidate.resolve()
            resolved.relative_to(site_dir)
        except ValueError:
            return None
        return resolved if resolved.is_file() else None

    def site_page_or_fallback(path: str | Path, title: str, fallback_body: str) -> FileResponse | HTMLResponse:
        file_path = safe_site_file(path)
        if file_path is not None:
            return _file_response(file_path, cache_control="public, max-age=300")
        return _public_html_page(title, fallback_body)

    def page_route(*paths: str, include_in_schema: bool = False):
        """GET plus HEAD for a public page.

        FastAPI's ``router.get`` registers GET alone — it does not add HEAD the
        way a bare Starlette route does — so every uptime monitor, link checker,
        and crawler that probes with HEAD got 405 from the marketing site's
        front door while browsers saw 200. ``/health`` already carried an
        explicit HEAD registration for exactly this reason; the public pages
        now get the same treatment in one place.
        """

        def decorate(endpoint):
            for path in paths:
                # HEAD is a separate, schema-hidden registration rather than a
                # second method on the GET route. A single route with
                # methods={"GET", "HEAD"} iterates that set when exporting
                # OpenAPI, and set order varies per process hash seed — the
                # committed contract then drifts between identical runs. Two
                # routes keep the behaviour and leave the schema deterministic,
                # with only GET documented.
                router.api_route(path, methods=["GET"], include_in_schema=include_in_schema)(endpoint)
                router.api_route(path, methods=["HEAD"], include_in_schema=False)(endpoint)
            return endpoint

        return decorate

    def public_page(*paths: str):
        """Register a page under each path and its trailing-slash twin.

        These are the URLs in PRIVACY_POLICY_URL, TERMS_URL, and
        ACCOUNT_DELETION_URL — the ones store reviewers open, crawlers follow,
        and people paste with a stray slash. Registered bare only, the slashed
        form fell through to the authenticated catch-all and answered a legal
        page request with 401 JSON. Registering both here means the next page
        added cannot reintroduce that.
        """

        def decorate(endpoint):
            for path in paths:
                for form in (path.rstrip("/"), path.rstrip("/") + "/"):
                    page_route(form)(endpoint)
            return endpoint

        return decorate

    @page_route("/", include_in_schema=True)
    async def root():
        return site_page_or_fallback(
            "index.html",
            "Thought Pins",
            """
            <p>Thought Pins is a private memory layer for journaling, reflection, source capture, and recall.</p>
            <p><a href="/app/">Open the web app</a></p>
            """,
        )

    @public_page("/privacy")
    async def privacy_page():
        return site_page_or_fallback(
            "privacy.html",
            "Privacy Policy",
            """
            <p>Thought Pins stores journal entries, imported documents, extracted memories, app preferences, devices, and account data so the memory assistant can work across sessions.</p>
            <h2>Data Use</h2>
            <p>Data is used to provide journal search, memory retrieval, reminders, account management, export, deletion, and AI-assisted answers. Production deployments should set a public PRIVACY_POLICY_URL with final legal text.</p>
            <h2>Controls</h2>
            <p>Authenticated users can export their data and request account deletion from the app or via the account deletion page.</p>
            """,
        )

    @public_page("/terms")
    async def terms_page():
        return site_page_or_fallback(
            "terms.html",
            "Terms",
            """
            <p>Thought Pins is a journaling and personal memory tool. Users are responsible for the content they submit and for complying with applicable laws and third-party rights.</p>
            <h2>Availability</h2>
            <p>Thought Pins is provided as a journaling and personal memory service. Production deployments should set a public TERMS_URL with final legal text.</p>
            """,
        )

    @public_page("/support")
    async def support_page():
        return site_page_or_fallback(
            "support.html",
            "Support",
            """
            <p>For local diagnostics, use the web app account tools or authenticated support workflows available in your deployment.</p>
            <p>Production deployments should set SUPPORT_URL to a public support page or mailto address.</p>
            """,
        )

    @public_page("/account/delete", "/delete-account")
    async def account_delete_page():
        return site_page_or_fallback(
            Path("account") / "delete" / "index.html",
            "Account Deletion",
            """
            <p>Signed-in users can delete their account from the web app Account screen. The API endpoint is DELETE /v1/me with confirmation set to DELETE.</p>
            <p>Deletion removes user-scoped journal entries, memories, entities, relationships, documents, jobs, sessions, devices, preferences, and audit-linked account data where supported by the backend lifecycle.</p>
            <p>Production deployments should set ACCOUNT_DELETION_URL to a public page with the final deletion workflow and support contact.</p>
            """,
        )

    @public_page("/ai-disclosure")
    async def ai_disclosure_page():
        return site_page_or_fallback(
            "ai-disclosure.html",
            "AI Disclosure",
            """
            <p>Thought Pins uses AI models to classify messages, extract memories, summarize documents, and answer questions from saved context. Answers can be incomplete or wrong and should be checked before important decisions.</p>
            <p>Thought Pins routes generation through the configured LLM provider and embeddings through the configured embedding provider.</p>
            """,
        )

    @public_page("/security")
    async def security_page():
        return site_page_or_fallback(
            "security.html",
            "Security",
            """
            <p>Thought Pins uses tenant-scoped access controls, encrypted transport in production, account sessions, audit events, and data export and deletion controls.</p>
            <p>Report suspected security issues privately to <a href="mailto:security@thoughtpins.com">security@thoughtpins.com</a>.</p>
            """,
        )

    @page_route("/classic", "/classic/")
    async def classic_home():
        """The alternate landing page linked from the homepage header and footer.

        Needs its own route: unlisted paths fall through to the authenticated
        API and answer 401, so the link would break for signed-out visitors.
        """
        return site_page_or_fallback(
            Path("classic") / "index.html",
            "Thought Pins",
            """
            <p>Thought Pins is a private memory layer for journaling, reflection, source capture, and recall.</p>
            <p><a href="/">Back to the current homepage</a></p>
            """,
        )

    @page_route("/robots.txt")
    async def robots_txt():
        file_path = safe_site_file("robots.txt")
        if file_path is None:
            raise HTTPException(status_code=404, detail="robots.txt not found")
        return _file_response(file_path, cache_control="public, max-age=300")

    @page_route("/sitemap.xml")
    async def sitemap_xml():
        file_path = safe_site_file("sitemap.xml")
        if file_path is None:
            raise HTTPException(status_code=404, detail="sitemap.xml not found")
        return _file_response(file_path, cache_control="public, max-age=300")

    @page_route("/assets/{path:path}")
    async def site_asset(path: str):
        file_path = safe_site_file(Path("assets") / path)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Public asset not found")
        return _file_response(file_path, cache_control="public, max-age=86400")

    @page_route("/app", "/app/", "/app/{path:path}")
    async def web_app(path: str = ""):
        file_path = safe_frontend_file(path)
        if file_path is None:
            asset_like = "." in Path(path).name
            file_path = None if asset_like else safe_frontend_file("")
        if file_path is None:
            raise HTTPException(status_code=404, detail="Frontend asset not found")
        cache_control = "no-store" if file_path.name == "index.html" else "public, max-age=300"
        return FileResponse(file_path, headers={"Cache-Control": cache_control})

    return router


def _resolve_frontend_dir() -> Path:
    dist_candidates = [
        config.resolve_path(Path("frontend") / "dist"),
        (Path.cwd() / "frontend" / "dist").resolve(),
    ]
    static_candidates = [
        config.resolve_path(Path("frontend") / "static"),
        (Path.cwd() / "frontend" / "static").resolve(),
        (Path(__file__).resolve().parent.parent / "web" / "static").resolve(),
    ]
    for candidate in dist_candidates:
        if (candidate / "index.html").is_file() and (candidate / _FRONTEND_BUILD_MARKER).is_file():
            return candidate
    for candidate in static_candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return static_candidates[0]


def _resolve_site_dir() -> Path:
    candidates = [
        config.resolve_path("site"),
        (Path.cwd() / "site").resolve(),
        (Path(__file__).resolve().parents[3] / "site").resolve(),
    ]
    for candidate in candidates:
        if (candidate / "privacy.html").is_file():
            return candidate
    return candidates[0]


def _file_response(path: Path, *, cache_control: str) -> FileResponse:
    return FileResponse(path, media_type=_media_type(path), headers={"Cache-Control": cache_control})


def _media_type(path: Path) -> str:
    return {
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".txt": "text/plain; charset=utf-8",
        ".webmanifest": "application/manifest+json; charset=utf-8",
        ".xml": "application/xml; charset=utf-8",
    }.get(path.suffix.lower(), "application/octet-stream")


def _public_html_page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - {config.APP_NAME}</title>
    <style>
      body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17211b; background: #f6f7f4; }}
      main {{ width: min(760px, calc(100% - 32px)); margin: 48px auto; padding: 24px; background: #fff; border: 1px solid #dce3dc; border-radius: 8px; }}
      h1 {{ margin: 0 0 16px; font-size: 28px; }}
      h2 {{ margin: 24px 0 8px; font-size: 18px; }}
      p, li {{ line-height: 1.55; }}
      a {{ color: #2f6f9f; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      {body}
    </main>
  </body>
</html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
