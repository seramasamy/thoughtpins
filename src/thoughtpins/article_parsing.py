"""HTML and provider-response normalization for public article retrieval."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from thoughtpins.article_types import FetchedSource
from thoughtpins.config import config


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical_url = ""
        self._tag_stack: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attr_map = {str(key).lower(): str(value) for key, value in attrs if key and value is not None}
        self._tag_stack.append(tag)
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (attr_map.get("name") or attr_map.get("property") or attr_map.get("itemprop") or "").lower()
            content = attr_map.get("content", "").strip()
            if key and content:
                self.meta.setdefault(key, content)
        if tag == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "").strip()
            if href and "canonical" in rel:
                self.canonical_url = href
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag in {"p", "br", "div", "li", "section", "article", "h1", "h2", "h3"}:
            self.body_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._tag_stack:
            self._tag_stack.pop()
        if tag in {"p", "li", "section", "article", "h1", "h2", "h3"}:
            self.body_parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = unescape(data or "").strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._skip_depth:
            return
        self.body_parts.append(text)
        self.body_parts.append(" ")

    @property
    def title(self) -> str:
        return _clean_text(" ".join(self.title_parts))[:512]

    @property
    def text(self) -> str:
        return _clean_text(" ".join(self.body_parts))


def _canonicalize_public_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"r", "s", "source", "publication_id", "triedredirect", "token"}
    ]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", urlencode(query), ""))


def _html_to_text(value: str) -> str:
    parser = _ReadableHtmlParser()
    parser.feed(value or "")
    return parser.text


def _finalize_fetched_source(
    *,
    original_url: str,
    url: str,
    title: str,
    text: str,
    source_domain: str,
    access_method: str,
    rights_basis: str,
    fetch_status: str,
    canonical_url: str,
    author: str | None = None,
    published_at: datetime | None = None,
    metadata: dict | None = None,
) -> FetchedSource:
    clean_text = _clean_text(text)
    canonical_url = _canonicalize_public_url(canonical_url or url)
    source_domain = source_domain or (urlparse(canonical_url).hostname or "")
    paywall_detected = _detect_paywall(clean_text)
    restricted_domain = any(
        _is_restricted_fetch_domain(value) for value in (original_url, url, canonical_url, source_domain)
    )
    quality = _retrieval_quality(clean_text, paywall_detected=paywall_detected)
    if paywall_detected or restricted_domain or len(clean_text) < config.ARTICLE_MIN_TEXT_CHARS:
        if restricted_domain:
            error = (
                "This publisher limits automated access. Thought Pins saved the source details and can use "
                "an authorized open copy when one is available."
            )
        elif paywall_detected:
            error = "The page appears access-gated, so only its public source details were retained."
        else:
            error = "The page did not expose enough public article text, so only its source details were retained."
        return FetchedSource(
            original_url=original_url,
            url=url,
            title=title[:512],
            # Metadata-only results must not leave provider-fetched article
            # text in the durable document row, even when it is excluded from
            # chunks and retrieval downstream.
            text="",
            status="needs_text",
            error=error,
            source_domain=source_domain,
            access_method=access_method,
            rights_basis="metadata_only",
            fetch_status=fetch_status,
            canonical_url=canonical_url,
            author=author,
            published_at=published_at,
            paywall_detected=paywall_detected,
            retrieval_quality_score=quality,
            metadata=(metadata or {})
            | {
                "chars": 0,
                "discarded_unusable_chars": len(clean_text),
            },
        )
    return FetchedSource(
        original_url=original_url,
        url=url,
        title=title[:512],
        text=clean_text,
        status="processed",
        source_domain=source_domain,
        access_method=access_method,
        rights_basis=rights_basis,
        fetch_status=fetch_status,
        canonical_url=canonical_url,
        author=author,
        published_at=published_at,
        paywall_detected=paywall_detected,
        retrieval_quality_score=quality,
        metadata=(metadata or {}) | {"chars": len(clean_text)},
    )


def _metadata_only_source(
    url: str,
    *,
    title: str,
    error: str,
    access_method: str = "metadata_only",
    fetch_status: str = "needs_text",
) -> FetchedSource:
    parsed = urlparse(url)
    return FetchedSource(
        original_url=url,
        url=url,
        title=title[:512],
        text="",
        status="needs_text" if fetch_status != "blocked" else "error",
        error=error,
        source_domain=parsed.hostname or "",
        access_method=access_method,
        rights_basis="metadata_only",
        fetch_status=fetch_status,
        canonical_url=url,
        retrieval_quality_score=0.0,
        metadata={"chars": 0},
    )


def _title_from_meta(parser: _ReadableHtmlParser, url: str) -> str:
    for key in ("og:title", "twitter:title", "headline", "name"):
        value = parser.meta.get(key, "").strip()
        if value:
            return _clean_text(value)[:512]
    return parser.title or _fallback_title(url)


def _author_from_meta(parser: _ReadableHtmlParser) -> str | None:
    for key in ("author", "article:author", "parsely-author", "twitter:creator"):
        value = parser.meta.get(key, "").strip()
        if value:
            return _clean_text(value)[:255]
    return None


def _published_from_meta(parser: _ReadableHtmlParser) -> datetime | None:
    for key in (
        "article:published_time",
        "article:modified_time",
        "date",
        "datepublished",
        "pubdate",
        "publishdate",
        "parsely-pub-date",
    ):
        parsed = _parse_datetime(parser.meta.get(key, ""))
        if parsed:
            return parsed
    return None


def _published_from_headers(headers) -> datetime | None:
    return _parse_datetime(headers.get("last-modified", ""))


def _parse_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_jina_markdown(text: str) -> tuple[str, str, dict]:
    title = ""
    body = text
    metadata: dict[str, str] = {}
    lines = text.splitlines()
    for line in lines[:20]:
        if line.startswith("Title:"):
            title = _clean_text(line.split(":", 1)[1])
            metadata["jina_title"] = title
        elif line.startswith("URL Source:"):
            metadata["jina_source"] = _clean_text(line.split(":", 1)[1])
        elif line.startswith("Published Time:"):
            metadata["published_time"] = _clean_text(line.split(":", 1)[1])
        elif line.startswith("Author:"):
            metadata["author"] = _clean_text(line.split(":", 1)[1])
    marker = "Markdown Content:"
    if marker in text:
        body = text.split(marker, 1)[1]
    return title, _clean_text(body), metadata


def _detect_paywall(text: str) -> bool:
    clean = _clean_text(text)
    lowered = clean.lower()
    hard_markers = (
        "subscribe to continue",
        "sign in to continue",
        "log in to continue",
        "subscription required",
        "register to continue",
        "create an account to continue",
        "you have reached your article limit",
        "to keep reading",
        "continue reading with",
        "members-only",
        "premium article",
        "paid subscribers only",
        "upgrade to read",
    )
    if any(marker in lowered for marker in hard_markers):
        return True

    # Public newsletters commonly contain "Subscribe now" and "Already a
    # subscriber?" as ordinary calls to action. Treat those as a gate only
    # when the fetched body is short and also signals subscriber-only access.
    promotional_markers = ("subscribe now", "already a subscriber")
    restricted_context = ("paid subscriber", "subscriber-only", "exclusive to subscribers", "unlock this post")
    return (
        len(clean) < max(config.ARTICLE_MIN_TEXT_CHARS * 3, 2_400)
        and any(marker in lowered for marker in promotional_markers)
        and any(marker in lowered for marker in restricted_context)
    )


def _is_restricted_fetch_domain(value: str) -> bool:
    # The personal offline build may retrieve from publishers the hosted service
    # will not, because its operator holds subscriptions to them and is reading
    # their own material. Config.validate_startup refuses to boot a staging or
    # production deployment with this on, so the public service cannot reach
    # this branch however it is configured.
    if config.ARTICLE_ALLOW_RESTRICTED_DOMAINS and not config.is_shared_deployment():
        return False
    parsed = urlparse(value if "://" in (value or "") else f"https://{value or ''}")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    for domain in config.ARTICLE_RESTRICTED_DOMAINS:
        normalized = (domain or "").strip().lower().rstrip(".")
        if normalized and (host == normalized or host.endswith(f".{normalized}")):
            return True
    return False


def _retrieval_quality(text: str, *, paywall_detected: bool) -> float:
    chars = len(_clean_text(text))
    if chars <= 0:
        return 0.0
    score = min(1.0, chars / 6_000)
    if chars >= config.ARTICLE_MIN_TEXT_CHARS:
        score = max(score, 0.35)
    if paywall_detected:
        score *= 0.45
    return round(score, 3)


def _fallback_title(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path:
        name = path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").strip()
        if name:
            return f"{parsed.netloc} - {name}"[:512]
    return parsed.netloc or "Saved source"


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return text.strip()
