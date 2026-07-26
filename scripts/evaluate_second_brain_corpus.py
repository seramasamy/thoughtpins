"""Live second-brain evaluation over a local multi-book public-domain corpus."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from console_output import force_utf8_stdio  # noqa: E402
from eval_runtime import (  # noqa: E402
    cleanup_eval_state,
    isolate_eval_state,
)

force_utf8_stdio()
EVAL_STATE = isolate_eval_state(ROOT, "second-brain-corpus")
from import_library_folder import import_folder  # noqa: E402

from thoughtpins.bot import commands  # noqa: E402
from thoughtpins.bot.commands import answer_with_llm, build_memory_context_package, handle_conversation  # noqa: E402
from thoughtpins.config import config  # noqa: E402
from thoughtpins.data_lifecycle import delete_user_data  # noqa: E402
from thoughtpins.db import DocumentSource, Memory, RawEntry, User  # noqa: E402
from thoughtpins.memory.search import search  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_user_for_telegram  # noqa: E402

DEFAULT_CORPUS = (
    Path.home()
    / "Desktop"
    / "thoughtpins_eval_corpus"
    / "Advisor Philosophy"
    / "Public Domain Test Series"
    / "Sherlock Holmes"
)

OFFLINE_BOOKS: tuple[tuple[str, str, str], ...] = (
    (
        "01-a-study-in-scarlet.txt",
        "A Study in Scarlet",
        "Holmes and Watson investigate a murder scene where RACHE is written on the wall. "
        "Holmes describes the case as a scarlet thread of murder running through ordinary life.",
    ),
    (
        "02-the-sign-of-the-four.txt",
        "The Sign of the Four",
        "Mary Morstan asks Holmes about missing pearls and her vanished father. "
        "The investigation leads to the Agra treasure and Tonga.",
    ),
    (
        "03-a-scandal-in-bohemia.txt",
        "A Scandal in Bohemia",
        "Irene Adler protects a photograph connected to the King of Bohemia. "
        "Holmes respects her judgment after she anticipates his plan.",
    ),
    (
        "04-the-final-problem.txt",
        "The Final Problem",
        "Professor Moriarty pursues Holmes to Reichenbach Falls. "
        "Watson finds evidence of their confrontation beside the falls.",
    ),
    (
        "05-the-empty-house.txt",
        "The Adventure of the Empty House",
        "Holmes returns and uses a wax figure to expose Colonel Moran. "
        "Moran fires a specialized air-gun toward the apparent figure in the Empty House.",
    ),
)

GUTENBERG_BOOKS: tuple[tuple[str, str, str], ...] = (
    ("01 A Study in Scarlet.txt", "A Study in Scarlet", "https://www.gutenberg.org/cache/epub/244/pg244.txt"),
    ("02 The Sign of the Four.txt", "The Sign of the Four", "https://www.gutenberg.org/cache/epub/2097/pg2097.txt"),
    (
        "03 The Adventures of Sherlock Holmes.txt",
        "The Adventures of Sherlock Holmes",
        "https://www.gutenberg.org/cache/epub/1661/pg1661.txt",
    ),
    (
        "04 The Memoirs of Sherlock Holmes.txt",
        "The Memoirs of Sherlock Holmes",
        "https://www.gutenberg.org/cache/epub/834/pg834.txt",
    ),
    (
        "05 The Return of Sherlock Holmes.txt",
        "The Return of Sherlock Holmes",
        "https://www.gutenberg.org/cache/epub/108/pg108.txt",
    ),
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


class FakeChat:
    async def send_action(self, action: str) -> None:
        return None


class FakeMessage:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.chat = FakeChat()
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, chat_id: str):
        self.message = FakeMessage(chat_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate reading-memory recall over a multi-book corpus.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--max-files", type=int, default=5)
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Generate a temporary deterministic five-book public-domain regression corpus.",
    )
    parser.add_argument(
        "--download-gutenberg",
        action="store_true",
        help="Download five complete public-domain Holmes books from Project Gutenberg into disposable state.",
    )
    parser.add_argument(
        "--skip-live-llm",
        action="store_true",
        help="Validate ingestion, retrieval, and context assembly without calling a hosted chat runtime.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.offline_fixture and args.download_gutenberg:
        parser.error("choose either --offline-fixture or --download-gutenberg")

    marker = "TPIN_SECOND_BRAIN_" + uuid4().hex[:10]
    chat_id = "synthetic-second-brain-" + marker
    user_id: str | None = None
    fixture_root = _create_offline_fixture(marker) if args.offline_fixture else None
    if args.download_gutenberg:
        fixture_root = _download_gutenberg_corpus()
    corpus = fixture_root if fixture_root is not None else args.corpus.expanduser()
    summary: dict[str, object] = {
        "marker": marker,
        "chat_id": chat_id,
        "corpus": (
            "temporary_project_gutenberg_download"
            if args.download_gutenberg
            else "temporary_public_domain_fixture"
            if fixture_root is not None
            else str(corpus)
        ),
        "corpus_mode": (
            "gutenberg_download"
            if args.download_gutenberg
            else "offline_fixture"
            if fixture_root is not None
            else "local_folder"
        ),
    }
    checks: list[Check] = []

    if not corpus.exists():
        checks = [Check("corpus path exists", False, str(corpus))]
        summary["cleanup"] = {"eval_state_removed": cleanup_eval_state(EVAL_STATE)}
        summary["checks"] = [check.__dict__ for check in checks]
        _print_summary(args.json, summary, checks)
        return 1

    init_db()
    session = get_session()
    try:
        user = get_or_create_user_for_telegram(chat_id, session=session)
        user_id = user.id
        session.close()

        import_stats = import_folder(
            corpus,
            user_id=user_id,
            telegram_chat_id=chat_id,
            source_type="public_domain_book",
            max_files=args.max_files,
        )
        summary["import"] = asdict(import_stats)
        duplicate_stats = import_folder(
            corpus,
            user_id=user_id,
            telegram_chat_id=chat_id,
            source_type="public_domain_book",
            max_files=args.max_files,
        )
        summary["duplicate_import"] = asdict(duplicate_stats)

        session = get_session()
        source_count = session.query(DocumentSource).filter(DocumentSource.user_id == user_id).count()
        memory_count = session.query(Memory).filter(Memory.user_id == user_id).count()
        summary["counts"] = {"sources": source_count, "memories": memory_count}
        summary["retrieval"] = _retrieval_snapshot(session, user_id)
        tenant_b = get_or_create_user_for_telegram(f"{chat_id}-tenant-b", session=session)
        summary["tenant_isolation_hits"] = len(
            search(
                "Reichenbach Falls Moriarty",
                session=session,
                user_id=tenant_b.id,
                include_private=True,
                limit=8,
            )
        )
        context = build_memory_context_package(
            "Connect Reichenbach Falls, the Empty House, Irene Adler, and Mary Morstan.",
            session,
            chat_id=chat_id,
            user_id=user_id,
            include_private=True,
            include_vault=False,
            max_chars=120_000,
        )
        summary["context"] = {
            "chars": len(context),
            "has_relevant_section": "QUERY-RELEVANT MEMORIES AND SOURCES" in context,
            "has_full_section": "FULL STRUCTURED JOURNAL DATABASE" in context,
            "mentions_reichenbach": "Reichenbach" in context,
            "mentions_empty_house": "Empty House" in context or "empty house" in context.lower(),
        }
        if args.skip_live_llm:
            summary["live_llm"] = "skipped_by_request"
        else:
            try:
                answer = answer_with_llm(
                    (
                        "Across the imported Sherlock Holmes books, identify which saved sources contain "
                        "Mary Morstan, Irene Adler, Reichenbach Falls, and the Empty House. Keep it concise."
                    ),
                    session,
                    user_id=user_id,
                )
                summary["answer"] = answer

                commands.CONVERSATION_CACHE[chat_id] = [
                    {"role": "user", "content": "I am using these books to test a second-brain corpus."},
                    {"role": "assistant", "content": "I will use source evidence from the imported library."},
                ]
                update = FakeUpdate(chat_id)
                import asyncio

                asyncio.run(handle_conversation(update, "how do Reichenbach and the Empty House connect?"))
                summary["chat_reply"] = update.message.replies[0] if update.message.replies else ""
                summary["live_llm"] = "passed"
            except Exception as exc:
                summary["live_llm"] = "failed"
                summary["llm_error"] = f"{type(exc).__name__}: hosted chat runtime unavailable"
        checks = _build_checks(summary, require_live_llm=not args.skip_live_llm)
    finally:
        if not args.keep_data:
            try:
                cleanup = _cleanup(session, user_id, chat_id, marker)
            except Exception as exc:
                session.close()
                cleanup = {"cleanup_error": type(exc).__name__}
            cleanup["eval_state_removed"] = cleanup_eval_state(EVAL_STATE)
            if fixture_root is not None:
                shutil.rmtree(fixture_root, ignore_errors=True)
                cleanup["fixture_removed"] = not fixture_root.exists()
            summary["cleanup"] = cleanup
        else:
            session.close()
            summary["cleanup"] = {"kept": True}

    passed = all(check.passed for check in checks)
    summary["checks"] = [check.__dict__ for check in checks]
    _print_summary(args.json, summary, checks)
    return 0 if passed else 1


def _create_offline_fixture(marker: str) -> Path:
    root = ROOT / ".tmp" / f"second-brain-corpus-{marker.lower()}"
    root.mkdir(parents=True, exist_ok=False)
    for filename, title, anchor in OFFLINE_BOOKS:
        chapters = [
            (
                f"Chapter {chapter}: {title}\n\n"
                f"{anchor} This deterministic public-domain regression note preserves the source title and "
                f"cross-book evidence while exercising chunk {chapter}, punctuation, and retrieval boundaries. "
                "It is intentionally a test fixture rather than a complete edition."
            )
            for chapter in range(1, 37)
        ]
        (root / filename).write_text("\n\n".join(chapters) + "\n", encoding="utf-8")
    return root


def _download_gutenberg_corpus() -> Path:
    root = EVAL_STATE.root / "gutenberg-holmes"
    root.mkdir(parents=True, exist_ok=False)
    for filename, _title, url in GUTENBERG_BOOKS:
        request = urllib.request.Request(url, headers={"User-Agent": "ThoughtPinsLiteraryEvaluation/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read(5_000_000)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Project Gutenberg download failed for {filename}: {type(exc).__name__}") from exc
        text = _trim_gutenberg_text(raw.decode("utf-8", errors="replace"))
        if len(text) < 50_000:
            raise RuntimeError(f"Project Gutenberg source was unexpectedly short: {filename}")
        (root / filename).write_text(text + "\n", encoding="utf-8", newline="\n")
    return root


def _trim_gutenberg_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    upper = normalized.upper()
    for marker in ("*** START OF THE PROJECT GUTENBERG", "*** START OF THIS PROJECT GUTENBERG"):
        position = upper.find(marker)
        if position >= 0:
            line_end = normalized.find("\n", position)
            if line_end >= 0:
                normalized = normalized[line_end + 1 :]
            break
    upper = normalized.upper()
    for marker in ("*** END OF THE PROJECT GUTENBERG", "*** END OF THIS PROJECT GUTENBERG"):
        position = upper.find(marker)
        if position >= 0:
            normalized = normalized[:position]
            break
    return normalized.strip()


def _print_summary(json_output: bool, summary: dict[str, object], checks: list[Check]) -> None:
    if json_output:
        print(json.dumps(summary, indent=2, default=str))
        return
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        suffix = f" - {check.detail}" if check.detail else ""
        print(f"{status}: {check.name}{suffix}")
    print(f"Summary: {sum(check.passed for check in checks)}/{len(checks)} passed")


def _retrieval_snapshot(session, user_id: str) -> dict[str, str]:
    queries = {
        "scarlet": "RACHE scarlet thread of murder",
        "sign_four": "Mary Morstan pearls Tonga",
        "adler": "Irene Adler Bohemia photograph",
        "reichenbach": "Reichenbach Falls Moriarty",
        "empty_house": "Empty House Colonel Moran air-gun",
    }
    snapshot: dict[str, str] = {}
    for name, query in queries.items():
        results = search(query, session=session, user_id=user_id, include_private=True, limit=8)
        snapshot[name] = "\n".join(f"{result.text}\n{result.evidence_text}" for result in results[:4])
    return snapshot


def _build_checks(summary: dict[str, object], *, require_live_llm: bool = True) -> list[Check]:
    import_stats = summary.get("import", {})
    if not isinstance(import_stats, dict):
        import_stats = {}
    duplicate_stats = summary.get("duplicate_import", {})
    if not isinstance(duplicate_stats, dict):
        duplicate_stats = {}
    counts = summary.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    retrieval = summary.get("retrieval", {})
    if not isinstance(retrieval, dict):
        retrieval = {}
    context = summary.get("context", {})
    if not isinstance(context, dict):
        context = {}
    answer = str(summary.get("answer", "")).lower()
    chat_reply = str(summary.get("chat_reply", "")).lower()

    checks = [
        Check("corpus files imported", int(import_stats.get("imported", 0)) >= 3, str(import_stats.get("imported", 0))),
        Check("document sources stored", int(counts.get("sources", 0)) >= 3, str(counts)),
        Check("document memories stored", int(counts.get("memories", 0)) >= 50, str(counts)),
        Check(
            "repeat import is idempotent",
            int(duplicate_stats.get("duplicates", 0)) >= 3 and int(duplicate_stats.get("imported", 0)) == 0,
            str({"duplicates": duplicate_stats.get("duplicates"), "imported": duplicate_stats.get("imported")}),
        ),
        Check("cross-tenant corpus search is empty", _coerce_int(summary.get("tenant_isolation_hits"), -1) == 0),
        Check("A Study in Scarlet detail retrievable", "rache" in str(retrieval.get("scarlet", "")).lower()),
        Check("The Sign of the Four detail retrievable", "morstan" in str(retrieval.get("sign_four", "")).lower()),
        Check("Irene Adler detail retrievable", "adler" in str(retrieval.get("adler", "")).lower()),
        Check("Reichenbach detail retrievable", "reichenbach" in str(retrieval.get("reichenbach", "")).lower()),
        Check("Empty House detail retrievable", "moran" in str(retrieval.get("empty_house", "")).lower()),
        Check(
            "smart context selected a memory section",
            bool(context.get("has_relevant_section") or context.get("has_full_section")),
            str(context),
        ),
    ]
    if require_live_llm:
        checks.extend(
            [
                Check(
                    "hosted answer completed", summary.get("live_llm") == "passed", str(summary.get("llm_error", ""))
                ),
                Check("answer mentions multiple imported anchors", _count_answer_anchors(answer) >= 3, answer[:300]),
                Check(
                    "chat uses corpus memory", "reichenbach" in chat_reply or "moriarty" in chat_reply, chat_reply[:300]
                ),
            ]
        )
    return checks


def _count_answer_anchors(answer: str) -> int:
    anchors = ("mary morstan", "irene adler", "reichenbach", "empty house", "moran", "moriarty")
    return sum(1 for anchor in anchors if anchor in answer)


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _cleanup(session, user_id: str | None, chat_id: str, marker: str) -> dict[str, object]:
    cleanup: dict[str, object] = {"db_deleted": {}, "vault_removed": False, "cache_removed": False}
    try:
        if user_id:
            cleanup["db_deleted"] = delete_user_data(session, user_id)
            cleanup["remaining_db_markers"] = (
                session.query(RawEntry).filter(RawEntry.raw_text.contains(marker)).count()
                + session.query(Memory).filter(Memory.text.contains(marker)).count()
                + session.query(User).filter(User.telegram_chat_id == chat_id).count()
            )
    finally:
        session.close()

    if user_id:
        vault_root = config.vault_path().resolve()
        vault_user_dir = (vault_root / user_id).resolve()
        if vault_user_dir.exists() and vault_root in vault_user_dir.parents:
            shutil.rmtree(vault_user_dir)
            cleanup["vault_removed"] = True

    commands.CONVERSATION_CACHE.pop(chat_id, None)
    commands._save_conversation_cache()
    cleanup["cache_removed"] = True
    try:
        from thoughtpins.memory.vector_store import close_vector_store

        close_vector_store()
        cleanup["vector_store_closed"] = True
    except Exception as exc:
        cleanup["vector_store_close_error"] = str(exc)
    return cleanup


if __name__ == "__main__":
    raise SystemExit(main())
