"""Portable library-note rendering with source-rights enforcement."""

from __future__ import annotations

from typing import Any

from thoughtpins.db import DocumentSource
from thoughtpins.source_policy import export_policy_for_source
from thoughtpins.vault.export_format import (
    _document_text_policy,
    _iso,
    _markdown_table,
    _metadata,
    _plain_list_items,
    _portable_document_summary,
    _string_list,
)
from thoughtpins.vault.markdown import (
    escape_wikilink_tokens,
    fenced_text,
    markdown_list,
    safe_markdown_heading,
)


def render_library_note(document: DocumentSource, related: list[str]) -> tuple[dict[str, Any], str]:
    """Return metadata and Markdown while honoring the source export policy."""
    analysis = document.metadata_json.get("reading_analysis", {}) if isinstance(document.metadata_json, dict) else {}
    topics = _plain_list_items(_string_list(analysis.get("topics", [])))
    concepts = _plain_list_items(_string_list(analysis.get("key_concepts", [])))
    metadata = _metadata(
        note_id=f"document-{document.id}",
        note_type="article" if document.source_type in {"url", "article"} else "document",
        title=document.title,
        created=_iso(document.created_at_utc),
        updated=_iso(document.created_at_utc),
        source=document.source_type,
        tags=["thoughtpins", "library", document.source_type or "document"],
        thoughtpins_id=document.id,
        related=related,
    )
    metadata.update(
        {
            "author": document.author or "",
            "publisher": document.source_domain or analysis.get("publisher") or "",
            "published": _iso(document.published_at) if document.published_at else "",
            "status": document.fetch_status or document.status,
            "rights_basis": document.rights_basis or "unknown",
            "topics": _string_list(analysis.get("topics", [])),
            "concepts": _string_list(analysis.get("key_concepts", [])),
        }
    )
    export_policy = export_policy_for_source(document)
    reading_card = _markdown_table(
        [
            ("Kind", document.source_type),
            ("Publisher", document.source_domain or analysis.get("publisher") or "unknown"),
            ("Author", document.author or "unknown"),
            ("Rights", document.rights_basis or "unknown"),
            ("Status", document.fetch_status or document.status),
            ("Access restricted", "yes" if document.paywall_detected else "no"),
        ]
    )
    lines = [
        f"# {safe_markdown_heading(document.title)}",
        "",
        "## Reading Card",
        reading_card,
        "",
        "## Source",
        f"- Type: {document.source_type}",
        f"- URL: {document.source_url or document.original_url or 'not provided'}",
        f"- Publisher/domain: {document.source_domain or analysis.get('publisher') or 'unknown'}",
        f"- Author: {document.author or 'unknown'}",
        f"- Access method: {document.access_method or 'unknown'}",
        f"- Rights basis: {document.rights_basis or 'unknown'}",
        f"- Fetch status: {document.fetch_status or document.status}",
        f"- Access restricted: {bool(document.paywall_detected)}",
        "",
        "## Topics",
        markdown_list(topics),
        "",
        "## Concepts",
        markdown_list(concepts),
        "",
        "## Related Thought Pins",
        markdown_list(related),
        "",
        "## Summary",
        escape_wikilink_tokens(
            _portable_document_summary(document, analysis, export_policy.include_extractive_summary),
        ),
        "",
        "## Text Policy",
        _document_text_policy(document),
    ]
    if document.raw_text and document.status == "processed" and export_policy.include_source_text:
        lines.extend(["", "## Extracted Text", fenced_text(document.raw_text)])
    elif document.processing_error:
        lines.extend(["", "## Retrieval Note", escape_wikilink_tokens(document.processing_error)])
    return metadata, "\n".join(lines)


__all__ = ["render_library_note"]
