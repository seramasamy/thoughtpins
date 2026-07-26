"""Safe public URL retrieval with optional reader-provider fallbacks."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger

from thoughtpins.article_parsing import (
    _author_from_meta,
    _canonicalize_public_url,
    _clean_text,
    _fallback_title,
    _finalize_fetched_source,
    _is_restricted_fetch_domain,
    _metadata_only_source,
    _published_from_headers,
    _published_from_meta,
    _ReadableHtmlParser,
    _title_from_meta,
)
from thoughtpins.article_providers import (
    _apify_actor_path,
    _apify_input_payload,
    _extract_apify_item,
    _fetch_with_apify,
    _fetch_with_firecrawl,
    _fetch_with_jina_reader,
    _fetch_with_substack_public_feed,
    _is_substack_url,
    _parse_substack_feed,
)
from thoughtpins.article_types import FetchedSource, _PublicHttpPayload
from thoughtpins.config import config
from thoughtpins_sources.open_access import OpenAccessCandidate, resolve_open_access

URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+", re.IGNORECASE)


__all__ = [
    "FetchedSource",
    "article_fetch_health",
    "extract_urls",
    "fetch_url_text",
    "_apify_actor_path",
    "_apify_input_payload",
    "_extract_apify_item",
    "_fetch_with_apify",
    "_fetch_with_firecrawl",
    "_fetch_with_jina_reader",
    "_fetch_with_local_http",
    "_finalize_fetched_source",
    "_parse_substack_feed",
    "_read_public_http_url",
    "_validate_fetch_url",
    "_validate_public_dns",
]


def extract_urls(text: str) -> list[str]:
    """Return unique http(s) URLs in text, preserving order."""
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def fetch_url_text(url: str) -> FetchedSource:
    """Fetch readable text from a public URL within publisher access rules."""
    safe, error = _validate_fetch_url(url)
    if not safe:
        return _metadata_only_source(url, title=_fallback_title(url), error=error, fetch_status="blocked")
    open_copy = _resolve_open_access_candidate(url)
    fetch_url = open_copy.url if open_copy is not None else url
    if _is_restricted_fetch_domain(url) and open_copy is None:
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error=(
                "This publisher limits automated access. Thought Pins saved the source details and can use "
                "an authorized open copy when one is available."
            ),
            access_method="metadata_only",
            fetch_status="restricted",
        )
    safe, error = _validate_fetch_url(fetch_url)
    if not safe or _is_restricted_fetch_domain(fetch_url):
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error=error or "The resolved source is not eligible for public retrieval.",
            access_method="metadata_only",
            fetch_status="blocked",
        )

    providers = _configured_fetch_providers()
    if _is_substack_url(fetch_url) and "substack" not in providers:
        # Substack publishes an official RSS feed for every publication. It is
        # cleaner and more stable than scraping the rendered newsletter shell.
        providers.insert(0, "substack")
    best: FetchedSource | None = None
    attempts: list[dict[str, str]] = []
    for provider in providers:
        try:
            if provider == "substack":
                fetched = _fetch_with_substack_public_feed(fetch_url)
            elif provider == "local":
                fetched = _fetch_with_local_http(fetch_url)
            elif provider == "jina":
                fetched = _fetch_with_jina_reader(fetch_url)
            elif provider == "firecrawl":
                fetched = _fetch_with_firecrawl(fetch_url)
            elif provider == "apify":
                fetched = _fetch_with_apify(fetch_url)
            else:
                attempts.append({"provider": provider, "status": "skipped", "error": "Unknown provider"})
                continue
        except Exception as exc:
            attempts.append({"provider": provider, "status": "error", "error": str(exc)[:200]})
            continue

        attempts.append({"provider": provider, "status": fetched.status, "error": fetched.error[:120]})
        if best is None or fetched.retrieval_quality_score > best.retrieval_quality_score:
            best = fetched
        if fetched.status == "processed":
            fetched.metadata["fetch_attempts"] = attempts
            return _apply_open_access_resolution(fetched, original_url=url, candidate=open_copy)

    if best is None:
        best = _metadata_only_source(
            url,
            title=_fallback_title(url),
            error="No configured article fetch provider could read this URL.",
        )
    best.metadata["fetch_attempts"] = attempts
    return _apply_open_access_resolution(best, original_url=url, candidate=open_copy)


def _resolve_open_access_candidate(url: str) -> OpenAccessCandidate | None:
    if not config.OPEN_ACCESS_RESOLUTION_ENABLED:
        return None
    try:
        return resolve_open_access(
            url,
            contact_email=config.OPEN_ACCESS_CONTACT_EMAIL,
            base_url=config.OPEN_ACCESS_BASE_URL,
            timeout_seconds=config.OPEN_ACCESS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("Open-access resolution was unavailable for this source: {}", str(exc)[:160])
        return None


def _apply_open_access_resolution(
    fetched: FetchedSource,
    *,
    original_url: str,
    candidate: OpenAccessCandidate | None,
) -> FetchedSource:
    if candidate is None:
        return fetched
    fetched.original_url = original_url
    fetched.rights_basis = candidate.rights_basis
    fetched.metadata["open_access_resolution"] = candidate.as_metadata()
    return fetched


def _configured_fetch_providers() -> list[str]:
    providers: list[str] = []
    seen: set[str] = set()
    for provider in config.ARTICLE_FETCH_PROVIDERS:
        normalized = (provider or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        providers.append(normalized)
    return providers or ["local"]


def article_fetch_health() -> dict[str, Any]:
    """Return article-reader diagnostics without exposing provider secrets."""
    providers = _configured_fetch_providers()
    known = {"local", "substack", "jina", "firecrawl", "apify"}
    unknown = [provider for provider in providers if provider not in known]
    paid_enabled = [
        provider
        for provider, ready in (
            ("firecrawl", bool(config.FIRECRAWL_API_KEY)),
            ("apify", bool(config.APIFY_API_TOKEN and config.APIFY_READER_ACTOR)),
        )
        if ready and provider in providers
    ]
    return {
        "status": "warn" if unknown else "configured",
        "providers": providers,
        "cheap_default": providers[:2] == ["local", "jina"],
        "jina": {
            "configured": "jina" in providers,
            "api_key_present": bool(config.JINA_API_KEY),
            "cost_tier": "free_or_low_cost_reader",
        },
        "firecrawl": {
            "configured": "firecrawl" in providers,
            "api_key_present": bool(config.FIRECRAWL_API_KEY),
            "cost_tier": "paid_public_web_extraction",
        },
        "apify": {
            "configured": "apify" in providers,
            "api_token_present": bool(config.APIFY_API_TOKEN),
            "actor_present": bool(config.APIFY_READER_ACTOR),
            "cost_tier": "paid_specialized_actor",
        },
        "paid_fallbacks_ready": paid_enabled,
        "substack_public_feed": True,
        "open_access_resolution": {
            "enabled": config.OPEN_ACCESS_RESOLUTION_ENABLED,
            "contact_email_present": bool(config.OPEN_ACCESS_CONTACT_EMAIL),
        },
        "unknown_providers": unknown,
        "restricted_domains_configured": len(config.ARTICLE_RESTRICTED_DOMAINS),
        "compliance": "public_sources_only; authorized_open_copy_or_metadata_for_restricted_sources",
    }


def _validate_fetch_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "Invalid URL. Only http(s) article links are supported."
    if parsed.username is not None or parsed.password is not None:
        return False, "URLs containing embedded credentials are blocked."
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return False, "Invalid URL host."
    if config.ARTICLE_ALLOW_PRIVATE_URLS and not config.is_production():
        return True, ""
    if host in {
        "localhost",
        "127.0.0.1",
        str(ipaddress.IPv4Address(0)),
    } or host.endswith((".local", ".internal", ".lan")):
        return False, "Private/local URLs are blocked for article fetching."
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved):
        return False, "Private/local IP URLs are blocked for article fetching."
    try:
        port = parsed.port
    except ValueError:
        return False, "Invalid URL port."
    if port not in {None, 80, 443} and not (config.ARTICLE_ALLOW_PRIVATE_URLS and not config.is_production()):
        return False, "Only standard web ports are supported for article fetching."
    return True, ""


def _fetch_with_local_http(url: str) -> FetchedSource:
    parsed = urlparse(url)
    payload = _read_public_http_url(url)
    content_type = payload.headers.get("content-type", "")
    content = payload.content
    final_url = payload.url
    source_domain = urlparse(final_url).hostname or parsed.hostname or ""
    metadata = {
        "content_type": content_type,
        "http_status": payload.status_code,
        "provider": "local",
    }
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        text = _clean_text(content.decode(payload.encoding or "utf-8", errors="replace"))
        title = _fallback_title(final_url)
        canonical_url = final_url
        author = None
        published_at = _published_from_headers(payload.headers)
    else:
        html = content.decode(payload.encoding or "utf-8", errors="replace")
        parser = _ReadableHtmlParser()
        parser.feed(html)
        text = parser.text
        title = _title_from_meta(parser, final_url)
        canonical_url = _canonicalize_public_url(
            urljoin(final_url, parser.canonical_url) if parser.canonical_url else final_url
        )
        author = _author_from_meta(parser)
        published_at = _published_from_meta(parser) or _published_from_headers(payload.headers)
        metadata["meta_keys"] = sorted(parser.meta)[:40]
        site_name = _clean_text(parser.meta.get("og:site_name", ""))
        if site_name:
            metadata["site_name"] = site_name[:255]
        if "substack" in html[:100_000].lower() or "substack" in site_name.lower():
            metadata["platform"] = "substack"

    return _finalize_fetched_source(
        original_url=url,
        url=final_url,
        title=title,
        text=text,
        source_domain=source_domain,
        access_method="public_fetch",
        rights_basis="public_web",
        fetch_status="fetched",
        canonical_url=canonical_url,
        author=author,
        published_at=published_at,
        metadata=metadata,
    )


def _read_public_http_url(url: str, *, client: httpx.Client | None = None) -> _PublicHttpPayload:
    """Read a bounded public response while validating every redirect hop."""
    owns_client = client is None
    http = client or httpx.Client(
        timeout=config.ARTICLE_FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": config.ARTICLE_USER_AGENT},
    )
    current_url = url
    try:
        for _ in range(6):
            safe, error = _validate_fetch_url(current_url)
            if not safe:
                raise ValueError(error)
            dns_safe, dns_error = _validate_public_dns(current_url)
            if not dns_safe:
                raise ValueError(dns_error)
            with http.stream("GET", current_url, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "").strip()
                    if not location:
                        raise httpx.HTTPStatusError(
                            "Redirect response did not include a Location header.",
                            request=response.request,
                            response=response,
                        )
                    current_url = urljoin(str(response.url), location)
                    continue
                response.raise_for_status()
                content = _read_bounded_response(response, config.ARTICLE_MAX_FETCH_BYTES)
                return _PublicHttpPayload(
                    url=str(response.url),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=content,
                    encoding=response.encoding or "utf-8",
                )
        raise httpx.TooManyRedirects("Article URL exceeded the five-redirect limit.")
    finally:
        if owns_client:
            http.close()


def _read_bounded_response(response: httpx.Response, limit: int) -> bytes:
    remaining = max(1, int(limit))
    content = bytearray()
    for chunk in response.iter_bytes():
        if not chunk:
            continue
        content.extend(chunk[:remaining])
        remaining -= min(len(chunk), remaining)
        if remaining <= 0:
            break
    return bytes(content)


def _validate_public_dns(url: str) -> tuple[bool, str]:
    if config.ARTICLE_ALLOW_PRIVATE_URLS and not config.is_production():
        return True, ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = {
            str(item[4][0]).split("%", 1)[0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if item[4]
        }
    except (OSError, socket.gaierror):
        return False, "Article host could not be resolved safely."
    if not addresses:
        return False, "Article host did not resolve to a public address."
    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address)
        except ValueError:
            return False, "Article host returned an invalid network address."
        if not resolved.is_global:
            return False, "Article host resolved to a private or reserved network address."
    return True, ""
