"""Import local text/PDF documents into Thought Pins reading memory."""

from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.library import ingest_document_text  # noqa: E402
from thoughtpins.store import get_session  # noqa: E402
from thoughtpins.users import get_or_create_user_for_telegram  # noqa: E402

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
PDF_EXTENSIONS = {".pdf"}
DEFAULT_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS


@dataclass
class ImportItem:
    path: str
    title: str
    status: str
    chars: int = 0
    chunks: int = 0
    memories: int = 0
    document_id: str = ""
    duplicate: bool = False
    error: str = ""


@dataclass
class ImportStats:
    root: str
    scanned: int
    imported: int
    duplicates: int
    skipped: int
    failed: int
    items: list[ImportItem]


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a local folder into Thought Pins reading memory.")
    parser.add_argument("folder", type=Path, help="Folder containing .txt/.md/.pdf documents.")
    parser.add_argument("--user-id", default="", help="Existing Thought Pins user id to import into.")
    parser.add_argument(
        "--telegram-chat-id",
        default="local-library-import",
        help="Telegram chat id used to create/bind an import user when --user-id is omitted.",
    )
    parser.add_argument("--source-type", default="book", help="Document source type label.")
    parser.add_argument("--max-files", type=int, default=0, help="Maximum files to import; 0 means all.")
    parser.add_argument(
        "--max-chars-per-file", type=int, default=0, help="Trim each file to this many chars; 0 means full."
    )
    parser.add_argument("--pdf-pages", type=int, default=250, help="Maximum PDF pages to extract per file.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and parse files without storing them.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    stats = import_folder(
        args.folder,
        user_id=args.user_id or None,
        telegram_chat_id=args.telegram_chat_id,
        source_type=args.source_type,
        max_files=args.max_files,
        max_chars_per_file=args.max_chars_per_file,
        pdf_pages=args.pdf_pages,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(asdict(stats), indent=2))
    else:
        print(
            f"Scanned {stats.scanned}; imported {stats.imported}; "
            f"duplicates {stats.duplicates}; skipped {stats.skipped}; failed {stats.failed}."
        )
        for item in stats.items:
            suffix = f" - {item.error}" if item.error else ""
            print(
                f"{item.status}: {item.title} ({item.chars} chars, chunks={item.chunks}, memories={item.memories}){suffix}"
            )
    return 0 if stats.failed == 0 else 1


def import_folder(
    folder: Path,
    *,
    user_id: str | None = None,
    telegram_chat_id: str = "local-library-import",
    source_type: str = "book",
    max_files: int = 0,
    max_chars_per_file: int = 0,
    pdf_pages: int = 250,
    dry_run: bool = False,
) -> ImportStats:
    root = folder.expanduser().resolve()
    files = _iter_document_files(root)
    if max_files > 0:
        files = files[:max_files]

    items: list[ImportItem] = []
    imported = duplicates = skipped = failed = 0
    session = get_session()
    try:
        owner_user_id = user_id
        if not owner_user_id and not dry_run:
            owner_user_id = get_or_create_user_for_telegram(telegram_chat_id, session=session).id
        for path in files:
            title = _title_for_path(path, root)
            rel_path = str(path.relative_to(root))
            try:
                text = read_document_text(path, pdf_pages=pdf_pages)
                if max_chars_per_file > 0:
                    text = text[:max_chars_per_file]
                if len(text.strip()) < 20:
                    skipped += 1
                    items.append(
                        ImportItem(path=rel_path, title=title, status="skipped", error="not enough readable text")
                    )
                    continue
                if dry_run:
                    imported += 1
                    items.append(ImportItem(path=rel_path, title=title, status="dry_run", chars=len(text)))
                    continue
                result = ingest_document_text(
                    session,
                    text,
                    user_id=owner_user_id,
                    telegram_chat_id=telegram_chat_id,
                    source_type=source_type,
                    title=title,
                    source_url=_source_url_for_path(path),
                    metadata_json={
                        "source_path": str(path),
                        "relative_path": rel_path,
                        "imported_at_utc": datetime.now(timezone.utc).isoformat(),
                        "size_bytes": path.stat().st_size,
                    },
                )
                if result.duplicate:
                    duplicates += 1
                    status = "duplicate"
                else:
                    imported += 1
                    status = "imported"
                items.append(
                    ImportItem(
                        path=rel_path,
                        title=result.title,
                        status=status,
                        chars=len(text),
                        chunks=result.chunks,
                        memories=result.memories,
                        document_id=result.document_id,
                        duplicate=result.duplicate,
                    )
                )
            except Exception as exc:
                failed += 1
                items.append(ImportItem(path=rel_path, title=title, status="failed", error=str(exc)[:500]))
    finally:
        session.close()
    return ImportStats(
        root=str(root),
        scanned=len(files),
        imported=imported,
        duplicates=duplicates,
        skipped=skipped,
        failed=failed,
        items=items,
    )


def read_document_text(path: Path, *, pdf_pages: int = 250) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is required for PDF import; install thoughtpins[telegram]") from exc
        with path.open("rb") as handle:
            reader = PdfReader(io.BytesIO(handle.read()))
        pages = []
        for page in reader.pages[:pdf_pages]:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages).strip()
    raise ValueError(f"Unsupported document type: {path.suffix}")


def _iter_document_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        return [root] if root.suffix.lower() in DEFAULT_EXTENSIONS else []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in DEFAULT_EXTENSIONS
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    )


def _title_for_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parent = rel.parent.name
    stem = path.stem.replace("_", " ").strip()
    return f"{parent} - {stem}" if parent and parent != "." else stem


def _source_url_for_path(path: Path) -> str | None:
    name = path.name.lower()
    if name.startswith("pg"):
        digits = []
        for char in name[2:]:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if digits:
            return f"https://www.gutenberg.org/ebooks/{''.join(digits)}"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
