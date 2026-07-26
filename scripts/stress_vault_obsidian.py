"""Stress-test Thought Pins vault export with a legal public corpus.

The script builds an isolated temporary SQLite database, imports a mixed corpus,
exports an Obsidian-compatible vault, validates it, optionally opens it in local
Obsidian, runs isolated parser checks, and removes temporary data by default.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import thoughtpins.library as library  # noqa: E402
import thoughtpins.store as store  # noqa: E402
from thoughtpins.config import config  # noqa: E402
from thoughtpins.db import Entity, EntityMention, Memory, RawEntry, Relationship  # noqa: E402
from thoughtpins.library import ingest_document_text  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_default_user  # noqa: E402
from thoughtpins.utils import hash_text  # noqa: E402
from thoughtpins.vault.exporter import VaultExporter  # noqa: E402
from thoughtpins.vault.markdown import parse_frontmatter  # noqa: E402
from thoughtpins.vault.validator import validate_vault  # noqa: E402


@dataclass(frozen=True)
class CorpusSource:
    key: str
    title: str
    kind: str
    url: str
    rights_basis: str
    author: str | None = None
    source_domain: str | None = None
    fallback_text: str = ""


PUBLIC_CORPUS: tuple[CorpusSource, ...] = (
    CorpusSource(
        key="study_in_scarlet",
        title="A Study in Scarlet",
        kind="book",
        url="https://www.gutenberg.org/cache/epub/244/pg244.txt",
        rights_basis="public_domain",
        author="Arthur Conan Doyle",
        source_domain="gutenberg.org",
    ),
    CorpusSource(
        key="sign_of_four",
        title="The Sign of the Four",
        kind="book",
        url="https://www.gutenberg.org/cache/epub/2097/pg2097.txt",
        rights_basis="public_domain",
        author="Arthur Conan Doyle",
        source_domain="gutenberg.org",
    ),
    CorpusSource(
        key="adventures_of_sherlock_holmes",
        title="The Adventures of Sherlock Holmes",
        kind="book",
        url="https://www.gutenberg.org/cache/epub/1661/pg1661.txt",
        rights_basis="public_domain",
        author="Arthur Conan Doyle",
        source_domain="gutenberg.org",
    ),
    CorpusSource(
        key="meditations",
        title="Meditations",
        kind="philosophy",
        url="https://www.gutenberg.org/cache/epub/2680/pg2680.txt",
        rights_basis="public_domain",
        author="Marcus Aurelius",
        source_domain="gutenberg.org",
    ),
    CorpusSource(
        key="modest_proposal",
        title="A Modest Proposal",
        kind="essay",
        url="https://www.gutenberg.org/cache/epub/1080/pg1080.txt",
        rights_basis="public_domain",
        author="Jonathan Swift",
        source_domain="gutenberg.org",
    ),
    CorpusSource(
        key="obsidian_properties",
        title="Obsidian Help: Properties",
        kind="article",
        url="https://raw.githubusercontent.com/obsidianmd/obsidian-help/master/en/Editing%20and%20formatting/Properties.md",
        rights_basis="official_public_web",
        author="Obsidian",
        source_domain="github.com/obsidianmd/obsidian-help",
    ),
    CorpusSource(
        key="obsidian_internal_links",
        title="Obsidian Help: Internal links",
        kind="article",
        url="https://raw.githubusercontent.com/obsidianmd/obsidian-help/master/en/Linking%20notes%20and%20files/Internal%20links.md",
        rights_basis="official_public_web",
        author="Obsidian",
        source_domain="github.com/obsidianmd/obsidian-help",
    ),
)

OFFLINE_FIXTURE = {
    source.key: (
        f"{source.title}\n\n"
        f"Public-domain or public-web compatibility fixture for {source.title}. "
        "This deterministic text is used only when --offline-fixture is selected for regression tests. "
        "It contains chapters, punctuation, unicode names like Zoë and São Paulo, and a fenced-looking [[link]] token "
        "to prove the vault validator does not treat source text as note structure.\n\n"
        "Chapter I. Observation and memory. The notes connect people, places, projects, and concepts. "
        "Chapter II. Repeated titles and long headings exercise filesystem boundaries. "
        "Chapter III. The exported vault remains ordinary Markdown.\n"
    )
    * 40
    for source in PUBLIC_CORPUS
}


@dataclass
class IsolatedCheckResult:
    ok: bool
    markdown_files: int
    manifest_ok: bool
    yaml_parser: str
    zip_roundtrip_ok: bool
    errors: list[str]


@dataclass
class StressResult:
    ok: bool
    temp_root: str
    cleaned: bool
    user_id: str
    corpus: list[dict[str, Any]]
    export_stats: dict[str, Any]
    validation: dict[str, Any]
    isolated_check: dict[str, Any]
    obsidian_probe: dict[str, Any]
    container_check: dict[str, Any]
    live_downloads: bool


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress-test the Thought Pins Obsidian vault exporter.")
    parser.add_argument("--temp-root", type=Path, default=None, help="Temporary work root. Defaults under .tmp.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary DB and vault for inspection.")
    parser.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Use deterministic local fixture text instead of network downloads.",
    )
    parser.add_argument("--max-source-chars", type=int, default=120_000, help="Maximum characters imported per source.")
    parser.add_argument(
        "--open-obsidian", action="store_true", help="Validate then hand the vault to a local Obsidian install."
    )
    parser.add_argument(
        "--obsidian-defaults", action="store_true", help="Write safe plugin-free .obsidian defaults before validation."
    )
    parser.add_argument(
        "--obsidian-wait-seconds",
        type=float,
        default=5.0,
        help="Wait after Obsidian launch before inspecting .obsidian.",
    )
    parser.add_argument(
        "--with-container",
        action="store_true",
        help="Attempt a Docker-based filesystem parser check if Docker is available.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    temp_root = (args.temp_root or ROOT / ".tmp" / f"vault-stress-{uuid4().hex[:12]}").resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    old_config = _override_runtime(temp_root)
    old_indexer = library._index_document_memories
    library._index_document_memories = lambda memories: None
    result: StressResult | None = None
    cleaned = False
    try:
        init_db()
        session = get_session()
        try:
            user = get_or_create_default_user(session=session)
            corpus_report = _import_corpus(
                session,
                user.id,
                offline=args.offline_fixture,
                max_chars=max(5_000, args.max_source_chars),
            )
            _seed_mixed_journal_graph(session, user.id)
            exporter = VaultExporter(session, user_id=user.id, vault_path=temp_root / "vault")
            export_stats = exporter.export_all(
                clean=True, validate=True, package_zip=True, obsidian_defaults=args.obsidian_defaults
            )
            vault_path = Path(exporter._vault)
            validation = validate_vault(vault_path)
            isolated = run_isolated_checks(vault_path)
            obsidian = _probe_obsidian(
                vault_path, open_obsidian=args.open_obsidian, wait_seconds=args.obsidian_wait_seconds
            )
            if args.open_obsidian:
                validation_after_open = validate_vault(vault_path)
                obsidian["post_open_validation"] = validation_after_open.as_dict()
            container = _container_check(vault_path, enabled=args.with_container)
            ok = (
                validation.ok
                and isolated.ok
                and container.get("ok", True)
                and not (args.open_obsidian and obsidian.get("load_result", "").startswith("launch_failed"))
            )
            result = StressResult(
                ok=ok,
                temp_root=str(temp_root),
                cleaned=False,
                user_id=user.id,
                corpus=corpus_report,
                export_stats=export_stats,
                validation=validation.as_dict(),
                isolated_check=asdict(isolated),
                obsidian_probe=obsidian,
                container_check=container,
                live_downloads=not args.offline_fixture,
            )
        finally:
            session.close()
    finally:
        library._index_document_memories = old_indexer
        _restore_runtime(old_config)
        if not args.keep_temp:
            _remove_tree(temp_root)
            cleaned = not temp_root.exists()
        if result is not None:
            result.cleaned = cleaned

    payload = asdict(result)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Vault stress result: {'passed' if result.ok else 'failed'}")
        print(f"Temp root cleaned: {result.cleaned}")
        print(f"Corpus sources: {len(result.corpus)}")
        print(f"Markdown files: {result.validation.get('checked_files')}")
        print(f"Validation errors: {len(result.validation.get('errors', []))}")
        print(f"Isolated check: {'passed' if result.isolated_check.get('ok') else 'failed'}")
        print(f"Obsidian load: {result.obsidian_probe.get('load_result')}")
        print(f"Container check: {result.container_check.get('status')}")
    return 0 if result.ok and result.cleaned or (result.ok and args.keep_temp) else 1


def _override_runtime(temp_root: Path) -> dict[str, tuple[Any, Any]]:
    db_path = temp_root / "thoughtpins-stress.sqlite3"
    vault_path = temp_root / "vault"
    qdrant_path = temp_root / "qdrant"
    overrides: dict[str, Any] = {
        "ENVIRONMENT": "development",
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "AUTO_CREATE_TABLES": True,
        "VAULT_PATH": vault_path,
        "VECTOR_MODE": "memory",
        "EMBEDDING_PROVIDER": "local",
        "GRAPH_PROVIDER": "internal_sql",
        "GRAPH_SHADOW_ENABLED": False,
        "LIBRARY_EXTRACT_GRAPH": False,
        "QDRANT_PATH": str(qdrant_path),
        "RUN_STARTUP_RECOVERY": False,
    }
    old = {key: (getattr(config, key), getattr(type(config), key)) for key in overrides}
    for key, value in overrides.items():
        setattr(config, key, value)
        setattr(type(config), key, value)
    if store._engine is not None:
        store._engine.dispose()
    store._engine = None
    store._SessionLocal = None
    return old


def _restore_runtime(old: dict[str, tuple[Any, Any]]) -> None:
    for key, (instance_value, class_value) in old.items():
        setattr(config, key, instance_value)
        setattr(type(config), key, class_value)
    if store._engine is not None:
        store._engine.dispose()
    store._engine = None
    store._SessionLocal = None


def _import_corpus(session, user_id: str, *, offline: bool, max_chars: int) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    duplicate_text = (
        "Duplicate title stress note with a different body so the filename collision path is exercised. " * 80
    )
    for index, source in enumerate(PUBLIC_CORPUS):
        text, status, error = _source_text(source, offline=offline, max_chars=max_chars)
        title = source.title
        if index == len(PUBLIC_CORPUS) - 1:
            title = "Duplicate Title: Research / Notes?"
        if index == len(PUBLIC_CORPUS) - 2:
            title = "Duplicate Title: Research / Notes?"
            text = text + "\n\n" + duplicate_text
        result = ingest_document_text(
            session,
            text,
            user_id=user_id,
            source_type="article" if source.kind == "article" else "book",
            title=title,
            author=source.author,
            original_url=source.url,
            source_url=source.url,
            canonical_url=source.url,
            source_domain=source.source_domain,
            access_method="offline_fixture" if offline else "public_http",
            rights_basis=source.rights_basis,
            fetch_status=status,
            paywall_detected=False,
            retrieval_quality_score=1.0 if status == "processed" else 0.4,
            status="processed",
            processing_error=None if status == "processed" else error,
            metadata_json={
                "stress_corpus_key": source.key,
                "stress_source_kind": source.kind,
                "source_url": source.url,
            },
        )
        report.append(
            {
                "key": source.key,
                "title": title,
                "kind": source.kind,
                "url": source.url,
                "rights_basis": source.rights_basis,
                "status": status,
                "chars_imported": len(text),
                "document_id": result.document_id,
                "chunks": result.chunks,
                "error": error,
            }
        )
    return report


def _source_text(source: CorpusSource, *, offline: bool, max_chars: int) -> tuple[str, str, str | None]:
    if offline:
        return OFFLINE_FIXTURE[source.key][:max_chars], "processed", None
    request = urllib.request.Request(source.url, headers={"User-Agent": "ThoughtPinsVaultStress/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(5_000_000)
        text = raw.decode("utf-8", errors="replace")
        text = _trim_public_text(text)
        if len(text.strip()) < 1_000:
            raise ValueError("downloaded source was too short for stress use")
        return text[:max_chars], "processed", None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        fallback = OFFLINE_FIXTURE[source.key][:max_chars]
        return fallback, "fallback_fixture", str(exc)[:240]


def _trim_public_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    start_markers = ("*** START OF THE PROJECT GUTENBERG", "*** START OF THIS PROJECT GUTENBERG")
    end_markers = ("*** END OF THE PROJECT GUTENBERG", "*** END OF THIS PROJECT GUTENBERG")
    upper = normalized.upper()
    for marker in start_markers:
        pos = upper.find(marker)
        if pos != -1:
            line_end = normalized.find("\n", pos)
            if line_end != -1:
                normalized = normalized[line_end + 1 :]
                upper = normalized.upper()
            break
    for marker in end_markers:
        pos = upper.find(marker)
        if pos != -1:
            normalized = normalized[:pos]
            break
    lines = [line.rstrip() for line in normalized.splitlines()]
    return "\n".join(lines).strip()


def _seed_mixed_journal_graph(session, user_id: str) -> None:
    now = datetime(2026, 6, 30, 15, 45, tzinfo=timezone.utc).replace(tzinfo=None)
    entries = [
        (
            "Quick bar note: met Zoë at Café Lumière; we discussed Project Atlas, São Paulo, and whether memory should feel calm.",
            "15:45",
        ),
        (
            "Long coffee chat reflection: Sherlock-style observation is useful, but Marcus Aurelius-style discipline matters more. "
            "I want Thought Pins to remember articles, books, date-night notes, recipes, and obscure details without commands.",
            "16:10",
        ),
        (
            "Recipe idea / duplicate title test: lemon, mint, black tea, and a tiny pinch of salt. Save this as a strange kitchen memory.",
            "18:30",
        ),
        (
            "Punctuation-heavy + unicode stress: Project Atlas: Vault/Export? [Obsidian] should survive filesystems; Café Lumière and Zoë remain linked.",
            "21:05",
        ),
    ]
    raw_entries: list[RawEntry] = []
    for text, local_time in entries:
        raw = RawEntry(
            user_id=user_id,
            created_at_utc=now,
            local_date=now.date(),
            local_time=local_time,
            source="vault_stress",
            raw_text=text,
            content_hash=hash_text(f"vault-stress-{local_time}-{text}"),
            processed_status="completed",
        )
        session.add(raw)
        raw_entries.append(raw)
    session.flush()

    entity_specs = [
        (
            "person",
            "Zoë",
            ["Zoe from the cafe"],
            [{"key": "tone", "value": "curious and direct", "confidence": "observed_by_user"}],
        ),
        (
            "place",
            "Café Lumière",
            ["Cafe Lumiere - downtown"],
            [{"key": "mood", "value": "quiet coffee spot", "confidence": "observed_by_user"}],
        ),
        (
            "project",
            "Project Atlas: Vault/Export? [Obsidian]",
            ["Atlas vault export"],
            [{"key": "status", "value": "active", "confidence": "observed_by_user"}],
        ),
        (
            "concept",
            "Sherlock-style observation",
            [],
            [{"key": "domain", "value": "attention and memory", "confidence": "inferred"}],
        ),
        (
            "concept",
            "Marcus Aurelius discipline",
            [],
            [{"key": "domain", "value": "philosophy", "confidence": "inferred"}],
        ),
        (
            "organization",
            "ThoughtPins",
            ["Thought Pins"],
            [{"key": "product", "value": "second brain journal", "confidence": "observed_by_user"}],
        ),
    ]
    entities: dict[str, Entity] = {}
    for entity_type, name, aliases, attributes in entity_specs:
        entity = Entity(
            user_id=user_id,
            type=entity_type,
            canonical_name=name,
            aliases_json=aliases,
            attributes_json=attributes,
            created_at_utc=now,
            updated_at_utc=now,
        )
        session.add(entity)
        entities[name] = entity
    session.flush()

    mention_plan = {
        0: ["Zoë", "Café Lumière", "Project Atlas: Vault/Export? [Obsidian]"],
        1: ["Sherlock-style observation", "Marcus Aurelius discipline", "ThoughtPins"],
        2: ["ThoughtPins"],
        3: ["Project Atlas: Vault/Export? [Obsidian]", "Café Lumière", "Zoë"],
    }
    for entry_index, names in mention_plan.items():
        for name in names:
            session.add(
                EntityMention(
                    user_id=user_id,
                    raw_entry_id=raw_entries[entry_index].id,
                    entity_id=entities[name].id,
                    surface_text=name,
                )
            )
    relationships = [
        ("Zoë", "Café Lumière", "met_at", raw_entries[0]),
        ("Zoë", "Project Atlas: Vault/Export? [Obsidian]", "discussed", raw_entries[0]),
        ("ThoughtPins", "Sherlock-style observation", "uses_concept", raw_entries[1]),
        ("ThoughtPins", "Marcus Aurelius discipline", "uses_concept", raw_entries[1]),
    ]
    for source_name, target_name, rel_type, raw in relationships:
        session.add(
            Relationship(
                user_id=user_id,
                source_entity_id=entities[source_name].id,
                target_entity_id=entities[target_name].id,
                relation_type=rel_type,
                raw_entry_id=raw.id,
                confidence="observed_by_user",
                first_seen_at=now,
                last_seen_at=now,
                evidence_count=1,
            )
        )
        session.add(
            Memory(
                user_id=user_id,
                raw_entry_id=raw.id,
                memory_type="observation",
                subject_entity_id=entities[source_name].id,
                object_entity_id=entities[target_name].id,
                predicate=rel_type,
                text=f"{source_name} {rel_type.replace('_', ' ')} {target_name} during vault stress testing.",
                local_date=raw.local_date,
                source_provenance=f"entry:{raw.id}",
                created_at_utc=now,
            )
        )
    session.commit()


def run_isolated_checks(vault_path: Path) -> IsolatedCheckResult:
    errors: list[str] = []
    markdown_files = sorted(vault_path.rglob("*.md"))
    manifest_ok = False
    manifest = vault_path / "_System" / "thoughtpins-vault-manifest.json"
    try:
        manifest_ok = json.loads(manifest.read_text(encoding="utf-8")).get("format") == "obsidian-compatible-vault"
    except Exception as exc:
        errors.append(f"manifest parse failed: {exc}")

    yaml_parser = "thoughtpins-simple-yaml"
    yaml_module: Any | None = None
    try:
        yaml_module = importlib.import_module("yaml")

        yaml_parser = "pyyaml"
    except ImportError:
        pass

    for path in markdown_files:
        rel = path.relative_to(vault_path).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            metadata, body = parse_frontmatter(text)
        except Exception as exc:
            errors.append(f"{rel}: simple frontmatter parse failed: {exc}")
            continue
        if yaml_module is not None:
            try:
                yaml_module.safe_load(text.split("---", 2)[1])
            except Exception as exc:
                errors.append(f"{rel}: PyYAML parse failed: {exc}")
        if "[[" in body and "```" in body:
            # The primary validator ignores fenced source text. This confirms the note is still parseable.
            parse_frontmatter(text)
        if not metadata.get("id") or not metadata.get("type"):
            errors.append(f"{rel}: missing id/type in isolated parser")

    zip_path = vault_path.with_suffix(".zip")
    zip_roundtrip_ok = False
    try:
        if zip_path.exists():
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                zip_roundtrip_ok = "Vault Home.md" in names and any(name.startswith("Library/") for name in names)
        else:
            errors.append("zip package is missing")
    except Exception as exc:
        errors.append(f"zip roundtrip failed: {exc}")

    ok = bool(markdown_files) and manifest_ok and zip_roundtrip_ok and not errors
    return IsolatedCheckResult(
        ok=ok,
        markdown_files=len(markdown_files),
        manifest_ok=manifest_ok,
        yaml_parser=yaml_parser,
        zip_roundtrip_ok=zip_roundtrip_ok,
        errors=errors,
    )


def _probe_obsidian(vault_path: Path, *, open_obsidian: bool, wait_seconds: float) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "scripts" / "probe_obsidian_vault.py"), str(vault_path), "--json"]
    if open_obsidian:
        command.insert(-1, "--open")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
    if completed.returncode not in {0, 1}:
        return {
            "load_result": "probe_failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "load_result": "probe_json_parse_failed",
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    if open_obsidian and payload.get("load_attempted"):
        time.sleep(max(0.0, wait_seconds))
    obsidian_dir = vault_path / ".obsidian"
    payload["obsidian_config_exists"] = obsidian_dir.exists()
    payload["obsidian_config_files"] = (
        sorted(path.relative_to(vault_path).as_posix() for path in obsidian_dir.rglob("*") if path.is_file())
        if obsidian_dir.exists()
        else []
    )
    return payload


def _container_check(vault_path: Path, *, enabled: bool) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not enabled:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "container check not requested; local isolated parser check ran",
        }
    if not docker:
        return {
            "ok": True,
            "status": "unavailable",
            "reason": "docker executable not found; local isolated parser check ran",
        }
    script = (
        "import pathlib, json; "
        "root=pathlib.Path('/vault'); "
        "files=list(root.rglob('*.md')); "
        "manifest=json.loads((root/'_System'/'thoughtpins-vault-manifest.json').read_text()); "
        "assert files and manifest.get('format')=='obsidian-compatible-vault'; "
        "print(len(files))"
    )
    completed = subprocess.run(
        [docker, "run", "--rm", "-v", f"{vault_path}:/vault:ro", "python:3.12-slim", "python", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    stderr = completed.stderr[-2000:]
    if completed.returncode != 0 and _docker_daemon_unavailable(stderr):
        return {
            "ok": True,
            "status": "unavailable",
            "reason": "docker executable found but daemon is not reachable; local isolated parser check ran",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": stderr,
        }
    return {
        "ok": completed.returncode == 0,
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": stderr,
    }


def _docker_daemon_unavailable(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(
        marker in lowered
        for marker in (
            "docker client must be run with elevated privileges",
            "cannot connect to the docker daemon",
            "is the docker daemon running",
            "the system cannot find the file specified",
            "error during connect",
        )
    )


def _remove_tree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass
    if path.exists():
        for _ in range(3):
            try:
                shutil.rmtree(path)
                return
            except Exception:
                time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
