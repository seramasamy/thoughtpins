"""Optional public reader-provider adapters for article retrieval."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from defusedxml import ElementTree as ET
from loguru import logger

from thoughtpins.article_parsing import (
    _canonicalize_public_url,
    _clean_text,
    _fallback_title,
    _finalize_fetched_source,
    _html_to_text,
    _metadata_only_source,
    _parse_datetime,
    _parse_jina_markdown,
)
from thoughtpins.article_types import FetchedSource
from thoughtpins.config import config


def _fetch_with_jina_reader(url: str) -> FetchedSource:
    reader_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": config.ARTICLE_USER_AGENT}
    if config.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {config.JINA_API_KEY}"
    with httpx.Client(timeout=config.ARTICLE_FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
        response = client.get(reader_url)
        response.raise_for_status()
        text = response.text[: config.ARTICLE_MAX_FETCH_BYTES]
    title, body, metadata = _parse_jina_markdown(text)
    canonical_url = _canonicalize_public_url(str(metadata.get("jina_source") or url))
    return _finalize_fetched_source(
        original_url=url,
        url=url,
        title=title or _fallback_title(url),
        text=body or text,
        source_domain=urlparse(url).hostname or "",
        access_method="jina_reader",
        rights_basis="public_web",
        fetch_status="fetched",
        canonical_url=canonical_url,
        author=str(metadata.get("author") or "").strip() or None,
        published_at=_parse_datetime(str(metadata.get("published_time") or "")),
        metadata=metadata | {"provider": "jina"},
    )


def _fetch_with_firecrawl(url: str) -> FetchedSource:
    if not config.FIRECRAWL_API_KEY:
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error="Firecrawl provider configured but FIRECRAWL_API_KEY is missing.",
            access_method="firecrawl",
            fetch_status="skipped",
        )
    endpoint = config.FIRECRAWL_BASE_URL.rstrip("/") + "/scrape"
    headers = {
        "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": config.ARTICLE_USER_AGENT,
    }
    payload = {"url": url, "formats": ["markdown"]}
    with httpx.Client(timeout=config.ARTICLE_FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    body = data.get("data") if isinstance(data, dict) else {}
    if not isinstance(body, dict):
        body = {}
    raw_metadata = body.get("metadata")
    metadata: dict = raw_metadata if isinstance(raw_metadata, dict) else {}
    markdown = str(body.get("markdown") or body.get("content") or "")[: config.ARTICLE_MAX_FETCH_BYTES]
    title = str(metadata.get("title") or metadata.get("ogTitle") or "").strip()
    source_url = str(
        metadata.get("canonicalUrl") or metadata.get("ogUrl") or metadata.get("sourceURL") or metadata.get("url") or url
    ).strip()
    source_url = _canonicalize_public_url(source_url)
    return _finalize_fetched_source(
        original_url=url,
        url=source_url or url,
        title=title or _fallback_title(url),
        text=markdown,
        source_domain=urlparse(source_url or url).hostname or "",
        access_method="firecrawl",
        rights_basis="public_web",
        fetch_status="fetched",
        canonical_url=source_url or url,
        author=str(metadata.get("author") or "").strip() or None,
        metadata={
            "provider": "firecrawl",
            "publication": str(metadata.get("ogSiteName") or metadata.get("siteName") or "").strip(),
            "firecrawl_metadata": metadata,
        },
    )


def _fetch_with_substack_public_feed(url: str) -> FetchedSource:
    """Read a public Substack post from the publication's official RSS feed."""
    origin = _substack_publication_origin(url)
    if not origin:
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error="This Substack link does not identify a public publication feed.",
            access_method="substack_rss",
            fetch_status="skipped",
        )

    feed_url = origin.rstrip("/") + "/feed"
    with httpx.Client(
        timeout=config.ARTICLE_FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": config.ARTICLE_USER_AGENT},
    ) as client:
        response = client.get(feed_url)
        response.raise_for_status()
        feed_text = response.text[: config.ARTICLE_MAX_FETCH_BYTES]

    item = _parse_substack_feed(feed_text, url)
    if item is None:
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error="The post was not available in the publication's public feed.",
            access_method="substack_rss",
            fetch_status="not_in_feed",
        )

    canonical_url = _canonicalize_public_url(str(item.get("url") or url))
    return _finalize_fetched_source(
        original_url=url,
        url=canonical_url,
        title=str(item.get("title") or _fallback_title(canonical_url)),
        text=str(item.get("text") or ""),
        source_domain=urlparse(canonical_url).hostname or urlparse(url).hostname or "",
        access_method="substack_rss",
        rights_basis="public_feed",
        fetch_status="fetched",
        canonical_url=canonical_url,
        author=str(item.get("author") or "").strip() or None,
        published_at=item.get("published_at") if isinstance(item.get("published_at"), datetime) else None,
        metadata={
            "provider": "substack_rss",
            "publication": str(item.get("publication") or "").strip(),
            "feed_url": feed_url,
        },
    )


def _parse_substack_feed(feed_text: str, target_url: str) -> dict[str, Any] | None:
    """Return the matching public RSS item without exposing unrelated posts."""
    try:
        root = ET.fromstring(feed_text)
    except ET.ParseError:
        return None

    channel = next((node for node in root.iter() if _xml_local_name(node.tag) == "channel"), root)
    publication = _xml_child_text(channel, "title")
    target_slug = _substack_post_slug(target_url)
    target_canonical = _canonicalize_public_url(target_url)

    for node in channel.iter():
        if _xml_local_name(node.tag) != "item":
            continue
        item_url = _xml_child_text(node, "link") or _xml_child_text(node, "guid")
        item_canonical = _canonicalize_public_url(item_url)
        item_slug = _substack_post_slug(item_url)
        if target_slug:
            if item_slug != target_slug:
                continue
        elif item_canonical != target_canonical:
            continue

        encoded = _xml_child_text(node, "encoded")
        description = _xml_child_text(node, "description")
        body = _html_to_text(encoded if len(encoded) >= len(description) else description)
        return {
            "title": _clean_text(_xml_child_text(node, "title")),
            "url": item_canonical or target_canonical,
            "text": body,
            "author": _clean_text(_xml_child_text(node, "creator") or _xml_child_text(node, "author")),
            "published_at": _parse_datetime(_xml_child_text(node, "pubDate")),
            "publication": _clean_text(publication),
        }
    return None


def _xml_child_text(node: ET.Element, local_name: str) -> str:
    for child in node:
        if _xml_local_name(child.tag) == local_name:
            return "".join(child.itertext()).strip()
    return ""


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _is_substack_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host == "open.substack.com" or host.endswith(".substack.com")


def _substack_publication_origin(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host == "open.substack.com":
        parts = [part for part in parsed.path.split("/") if part]
        if "pub" in parts:
            index = parts.index("pub") + 1
            if index < len(parts) and re.fullmatch(r"[a-z0-9-]+", parts[index], re.IGNORECASE):
                return f"https://{parts[index].lower()}.substack.com"
        return ""
    if host.endswith(".substack.com") and host not in {"www.substack.com", "substack.com"}:
        return f"{parsed.scheme or 'https'}://{host}"
    return ""


def _substack_post_slug(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if "p" not in parts:
        return ""
    index = parts.index("p") + 1
    return parts[index].lower() if index < len(parts) else ""


def _fetch_with_apify(url: str) -> FetchedSource:
    if not config.APIFY_API_TOKEN or not config.APIFY_READER_ACTOR:
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error="Apify provider configured but APIFY_API_TOKEN or APIFY_READER_ACTOR is missing.",
            access_method="apify",
            fetch_status="skipped",
        )

    actor_id = _apify_actor_path(config.APIFY_READER_ACTOR)
    endpoint = config.APIFY_BASE_URL.rstrip("/") + f"/acts/{actor_id}/run-sync-get-dataset-items"
    headers = {
        "Authorization": f"Bearer {config.APIFY_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": config.ARTICLE_USER_AGENT,
    }
    payload = _apify_input_payload(url)
    with httpx.Client(timeout=config.ARTICLE_FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()

    items = data if isinstance(data, list) else data.get("items") if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []
    item = next((candidate for candidate in items if isinstance(candidate, dict)), {})
    if not item:
        return _metadata_only_source(
            url,
            title=_fallback_title(url),
            error="Apify actor returned no readable dataset items.",
            access_method="apify",
            fetch_status="fetched",
        )

    title, body, metadata = _extract_apify_item(item, url)
    source_url = _first_string(item, ("url", "sourceUrl", "sourceURL", "loadedUrl", "canonicalUrl")) or url
    return _finalize_fetched_source(
        original_url=url,
        url=source_url,
        title=title or _fallback_title(url),
        text=body,
        source_domain=urlparse(source_url).hostname or urlparse(url).hostname or "",
        access_method="apify",
        rights_basis="public_web",
        fetch_status="fetched",
        canonical_url=source_url,
        author=_first_string(item, ("author", "byline")) or None,
        metadata={
            "provider": "apify",
            "apify_actor": config.APIFY_READER_ACTOR,
            "apify_metadata": metadata,
        },
    )


def _apify_actor_path(actor: str) -> str:
    # Apify URL paths conventionally use username~actor-name even when humans
    # write actor identifiers as username/actor-name.
    return quote((actor or "").strip().replace("/", "~"), safe="~")


def _apify_input_payload(url: str) -> dict[str, Any]:
    template = (config.APIFY_READER_INPUT_TEMPLATE or "").strip()
    if template:
        try:
            rendered = template.replace("{url}", url)
            parsed = json.loads(rendered)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.warning("Invalid APIFY_READER_INPUT_TEMPLATE; using default input: {}", str(exc)[:120])
    return {
        "startUrls": [{"url": url}],
        "maxCrawlPages": 1,
    }


def _extract_apify_item(item: dict[str, Any], url: str) -> tuple[str, str, dict[str, Any]]:
    raw_metadata = item.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    title = (
        _first_string(item, ("title", "pageTitle", "headline", "name"))
        or _first_string(metadata, ("title", "ogTitle", "headline"))
        or ""
    )
    body = _first_string(
        item,
        (
            "markdown",
            "text",
            "content",
            "articleText",
            "body",
            "description",
        ),
    )
    if not body:
        html_body = _first_string(item, ("html", "pageHtml"))
        if html_body:
            body = _html_to_text(html_body)
    apify_metadata = {
        "item_keys": sorted(str(key) for key in item.keys())[:40],
        "source_url": _first_string(item, ("url", "sourceUrl", "sourceURL", "loadedUrl", "canonicalUrl")) or url,
    }
    if metadata:
        apify_metadata["metadata_keys"] = sorted(str(key) for key in metadata.keys())[:40]
    return _clean_text(title), _clean_text(body), apify_metadata


def _first_string(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
