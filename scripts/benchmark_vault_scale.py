"""Measure portable-vault behavior at realistic large-account sizes."""

from __future__ import annotations

import argparse
import gc
import hashlib
import io
import json
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psutil
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from thoughtpins.db import Base, RawEntry, User
from thoughtpins.vault.exporter import VaultExporter
from thoughtpins.vault.importer import import_obsidian_vault

ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class BenchmarkResult:
    workload: str
    items: int
    seconds: float
    items_per_second: float
    peak_rss_mib: float
    artifact_mib: float
    checks: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-notes", type=int, default=10_000)
    parser.add_argument("--import-notes", type=int, default=100_000)
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()
    if not 1 <= args.export_notes <= 100_000:
        parser.error("--export-notes must be from 1 to 100000")
    if not 1 <= args.import_notes <= 100_000:
        parser.error("--import-notes must be from 1 to 100000")

    with tempfile.TemporaryDirectory(prefix="thoughtpins-vault-scale-") as temporary:
        workspace = Path(temporary)
        export_result = benchmark_export(workspace, args.export_notes)
        gc.collect()
        import_result = benchmark_import_preview(workspace, args.import_notes)

    report = {
        "app": "Thought Pins",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(export_result), asdict(import_result)],
    }
    report_path = (
        Path(args.report_path)
        if args.report_path
        else (ROOT / "reports" / f"vault-scale-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"report={report_path}")
    return 0


def benchmark_export(workspace: Path, note_count: int) -> BenchmarkResult:
    database_path = workspace / "scale.sqlite3"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    user_id = "vault-scale-user"
    try:
        session.add(User(id=user_id, api_key="vault-scale-api-key", display_name="Vault Scale"))
        session.commit()
        start_at = datetime(2020, 1, 1, 12, 0)
        batch_size = 2_000
        for offset in range(0, note_count, batch_size):
            rows = []
            for index in range(offset, min(note_count, offset + batch_size)):
                created = start_at + timedelta(minutes=index)
                text = f"Entry {index}: a bounded observation about durable memory, provenance, and a quiet walk."
                rows.append(
                    {
                        "id": f"e{index:015d}",
                        "user_id": user_id,
                        "created_at_utc": created,
                        "local_date": created.date(),
                        "local_time": created.strftime("%H:%M"),
                        "source": "scale_test",
                        "raw_text": text,
                        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                        "is_private": False,
                        "sensitivity": "personal",
                        "processed_status": "completed",
                        "user_importance": index % 5 + 1,
                        "importance_source": "user",
                    }
                )
            session.execute(insert(RawEntry), rows)
            session.commit()

        gc.collect()
        memory = PeakRssSampler()
        started = time.perf_counter()
        with memory:
            exporter = VaultExporter(session, user_id=user_id, vault_path=workspace / "vault")
            stats = exporter.export_all(validate=True, package_zip=True, obsidian_defaults=True)
        elapsed = time.perf_counter() - started
        zip_path = Path(stats["zip_path"])
        return BenchmarkResult(
            workload="export_and_validate",
            items=note_count,
            seconds=round(elapsed, 3),
            items_per_second=round(note_count / max(elapsed, 0.001), 2),
            peak_rss_mib=memory.peak_mib,
            artifact_mib=round(zip_path.stat().st_size / (1024 * 1024), 2),
            checks={
                "entries": stats["entries"],
                "validation_errors": stats["validation_errors"],
                "validation_warnings": stats["validation_warnings"],
                "vault_files": stats["vault_files"],
                "validation_findings": (
                    exporter.validation_result.as_dict()["errors"][:10] if exporter.validation_result else []
                ),
            },
        )
    finally:
        session.close()
        engine.dispose()


def benchmark_import_preview(workspace: Path, note_count: int) -> BenchmarkResult:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED, allowZip64=True) as package:
        package.writestr("Scale Vault/.obsidian/app.json", "{}")
        for index in range(note_count):
            package.writestr(
                f"Scale Vault/Notes/{index // 1000:03d}/Note {index:06d}.md",
                f"# Note {index}\n\nBounded source note {index} about memory structure and provenance.",
            )
    archive = stream.getvalue()

    database_path = workspace / "preview.sqlite3"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    user_id = "vault-preview-user"
    try:
        session.add(User(id=user_id, api_key="vault-preview-api-key", display_name="Vault Preview"))
        session.commit()
        gc.collect()
        memory = PeakRssSampler()
        started = time.perf_counter()
        with memory:
            result = import_obsidian_vault(
                session,
                user_id=user_id,
                filename="scale-vault.zip",
                archive=archive,
                dry_run=True,
                enqueue_jobs=False,
            )
        elapsed = time.perf_counter() - started
        return BenchmarkResult(
            workload="import_preview",
            items=note_count,
            seconds=round(elapsed, 3),
            items_per_second=round(note_count / max(elapsed, 0.001), 2),
            peak_rss_mib=memory.peak_mib,
            artifact_mib=round(len(archive) / (1024 * 1024), 2),
            checks={
                "notes_discovered": result.notes_discovered,
                "new_notes": result.new_notes,
                "errors": len(result.errors),
                "preview_items_returned": len(result.preview_items),
                "writes_performed": result.imported,
            },
        )
    finally:
        session.close()
        engine.dispose()


class PeakRssSampler:
    """Sample resident memory without slowing file-heavy workloads like tracemalloc."""

    def __init__(self, interval_seconds: float = 0.05) -> None:
        self._process = psutil.Process()
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak_bytes = self._process.memory_info().rss

    @property
    def peak_mib(self) -> float:
        return round(self._peak_bytes / (1024 * 1024), 2)

    def __enter__(self) -> PeakRssSampler:
        self._thread = threading.Thread(target=self._sample, name="vault-rss-sampler", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self._peak_bytes = max(self._peak_bytes, self._process.memory_info().rss)
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _sample(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._peak_bytes = max(self._peak_bytes, self._process.memory_info().rss)
            except psutil.Error:
                return


if __name__ == "__main__":
    raise SystemExit(main())
