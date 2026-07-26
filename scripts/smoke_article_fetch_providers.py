"""Smoke-test article reader providers without saving anything.

This intentionally tests public/authorized pages only. For restricted sources,
Thought Pins should save metadata and ask the user to paste or upload text they
can access instead of trying to bypass access controls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins import article_fetch  # noqa: E402
from thoughtpins.article_fetch import FetchedSource  # noqa: E402
from thoughtpins.config import config  # noqa: E402

DEFAULT_PUBLIC_URLS = [
    "https://www.paulgraham.com/greatwork.html",
    "https://www.gutenberg.org/cache/epub/1342/pg1342.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test configured article reader providers.")
    parser.add_argument("--url", action="append", default=[], help="Public URL to test. Can be repeated.")
    parser.add_argument(
        "--chain-only",
        action="store_true",
        help="Only test the configured provider chain, not individual providers.",
    )
    parser.add_argument(
        "--expect-needs-text",
        action="store_true",
        help="Pass when the chain stores metadata-only and asks for user-provided text.",
    )
    args = parser.parse_args()

    urls = args.url or DEFAULT_PUBLIC_URLS
    health = article_fetch.article_fetch_health()
    print(
        json.dumps(
            {
                "providers": health["providers"],
                "jina_key_present": health["jina"]["api_key_present"],
                "firecrawl_key_present": health["firecrawl"]["api_key_present"],
                "paid_fallbacks_ready": health["paid_fallbacks_ready"],
                "compliance": health["compliance"],
            },
            indent=2,
        )
    )

    failures: list[str] = []
    for url in urls:
        chain = article_fetch.fetch_url_text(url)
        _print_result("chain", url, chain)
        if args.expect_needs_text:
            if chain.status != "needs_text" or chain.rights_basis != "metadata_only":
                failures.append(f"chain should require user text for {url}: status={chain.status}")
        elif chain.status != "processed":
            failures.append(f"chain could not process {url}: {chain.error}")

        if args.chain_only:
            continue
        for name, fetcher in _individual_fetchers():
            result = _safe_fetch(fetcher, url)
            _print_result(name, url, result)
            if name in {"jina", "firecrawl"} and _provider_configured(name) and result.status != "processed":
                failures.append(f"{name} did not process {url}: {result.error}")

    if failures:
        print("Article provider smoke failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Article provider smoke passed.")
    return 0


def _individual_fetchers() -> list[tuple[str, Callable[[str], FetchedSource]]]:
    return [
        ("local", article_fetch._fetch_with_local_http),
        ("jina", article_fetch._fetch_with_jina_reader),
        ("firecrawl", article_fetch._fetch_with_firecrawl),
    ]


def _provider_configured(name: str) -> bool:
    if name == "jina":
        return "jina" in config.ARTICLE_FETCH_PROVIDERS
    if name == "firecrawl":
        return "firecrawl" in config.ARTICLE_FETCH_PROVIDERS and bool(config.FIRECRAWL_API_KEY)
    return name in config.ARTICLE_FETCH_PROVIDERS


def _safe_fetch(fetcher: Callable[[str], FetchedSource], url: str) -> FetchedSource:
    try:
        return fetcher(url)
    except Exception as exc:
        return FetchedSource(
            original_url=url,
            url=url,
            status="error",
            error=str(exc)[:240],
            access_method=getattr(fetcher, "__name__", "provider"),
        )


def _print_result(provider: str, url: str, result: FetchedSource) -> None:
    print(
        json.dumps(
            {
                "provider": provider,
                "url": url,
                "status": result.status,
                "access_method": result.access_method,
                "rights_basis": result.rights_basis,
                "chars": len(result.text or ""),
                "quality": result.retrieval_quality_score,
                "paywall_detected": result.paywall_detected,
                "title": result.title[:120],
                "error": result.error[:160],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
