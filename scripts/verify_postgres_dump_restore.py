"""Prove PostgreSQL logical backup recovery against an isolated scratch database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SAFE_PROJECT_RE = re.compile(r"^thoughtpins-[a-z0-9][a-z0-9-]{0,50}$")
SAFE_WSL_DISTRO_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
SAFE_SCRATCH_DATABASE_RE = re.compile(r"^thoughtpins_restore_drill_[a-f0-9]{12}$")


class DatabaseSnapshot(TypedDict):
    rows: dict[str, int]
    policies: list[tuple[Any, ...]]
    rls: list[tuple[str, bool, bool]]
    alembic_versions: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Owner PostgreSQL URL used for fixture setup and verification.",
    )
    parser.add_argument("--compose-project", required=True, help="Scoped Compose project containing PostgreSQL.")
    parser.add_argument("--compose-service", default="postgres")
    parser.add_argument("--database-user", default="", help="Role used by pg_dump and pg_restore inside PostgreSQL.")
    parser.add_argument("--wsl-distro", default="", help="Optional Windows WSL distribution hosting Docker.")
    parser.add_argument("--report-path", default="reports/postgres-restore-current.json")
    args = parser.parse_args()

    source_url = make_url(args.database_url)
    if source_url.get_backend_name() != "postgresql" or not source_url.database:
        raise ValueError("--database-url must identify a PostgreSQL database")
    assert_safe_project(args.compose_project)
    assert_safe_identifier(args.compose_service, label="Compose service")
    database_user = args.database_user or source_url.username or "postgres"
    assert_safe_identifier(database_user, label="database user")

    scratch_database = f"thoughtpins_restore_drill_{uuid4().hex[:12]}"
    fixture_suffix = uuid4().hex[:12]
    fixture_user = f"backup_drill_user_{fixture_suffix}"
    fixture_entry = f"backup_drill_entry_{fixture_suffix}"
    fixture_hash = hashlib.sha256(fixture_entry.encode("utf-8")).hexdigest()
    source_engine = create_engine(source_url, future=True, pool_pre_ping=True)
    admin_engine = create_engine(_database_url(source_url, "postgres"), future=True, isolation_level="AUTOCOMMIT")
    restored_engine = None
    dump_path: Path | None = None
    created_scratch = False
    fixture_inserted = False

    try:
        _insert_fixture(source_engine, fixture_user, fixture_entry, fixture_hash)
        fixture_inserted = True
        source_snapshot = _database_snapshot(source_engine)

        with tempfile.NamedTemporaryFile(prefix="thoughtpins-postgres-", suffix=".dump", delete=False) as handle:
            dump_path = Path(handle.name)
            _run(
                [
                    *_compose_command(args.wsl_distro, args.compose_project),
                    "exec",
                    "-T",
                    args.compose_service,
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    database_user,
                    "--dbname",
                    source_url.database,
                ],
                stdout=handle,
            )
        if dump_path.stat().st_size < 1_024:
            raise RuntimeError("PostgreSQL dump was unexpectedly small")

        _create_scratch_database(admin_engine, scratch_database, database_user)
        created_scratch = True
        with dump_path.open("rb") as handle:
            _run(
                [
                    *_compose_command(args.wsl_distro, args.compose_project),
                    "exec",
                    "-T",
                    args.compose_service,
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    database_user,
                    "--dbname",
                    scratch_database,
                ],
                stdin=handle,
            )

        restored_engine = create_engine(
            _database_url(source_url, scratch_database),
            future=True,
            pool_pre_ping=True,
        )
        restored_snapshot = _database_snapshot(restored_engine)
        if source_snapshot != restored_snapshot:
            raise RuntimeError(_snapshot_difference(source_snapshot, restored_snapshot))
        with restored_engine.connect() as conn:
            restored_fixture = conn.execute(
                text(
                    "SELECT count(*) FROM raw_entries "
                    "WHERE id = :entry_id AND user_id = :user_id AND content_hash = :content_hash"
                ),
                {"entry_id": fixture_entry, "user_id": fixture_user, "content_hash": fixture_hash},
            ).scalar_one()
        if restored_fixture != 1:
            raise RuntimeError("Restored database did not preserve the recovery fixture")

        dump_bytes = dump_path.stat().st_size
        dump_sha256 = hashlib.sha256(dump_path.read_bytes()).hexdigest()
        restored_engine.dispose()
        restored_engine = None
        _drop_scratch_database(admin_engine, scratch_database)
        created_scratch = False
        _delete_fixture(source_engine, fixture_user)
        fixture_inserted = False
        dump_path.unlink()
        dump_path = None

        report = {
            "schema_version": 1,
            "status": "passed",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "compose_project": args.compose_project,
            "source_database": source_url.database,
            "scratch_database_prefix": "thoughtpins_restore_drill_",
            "dump_bytes": dump_bytes,
            "dump_sha256": dump_sha256,
            "public_tables": len(source_snapshot["rows"]),
            "total_rows": sum(source_snapshot["rows"].values()),
            "rls_tables": sum(1 for item in source_snapshot["rls"] if item[1]),
            "policies": len(source_snapshot["policies"]),
            "alembic_versions": source_snapshot["alembic_versions"],
            "fixture_restored": True,
            "scratch_database_removed": True,
            "dump_removed": True,
        }
        report_path = Path(args.report_path)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    finally:
        cleanup_errors: list[str] = []
        if restored_engine is not None:
            restored_engine.dispose()
        if created_scratch:
            try:
                _drop_scratch_database(admin_engine, scratch_database)
            except Exception as exc:
                cleanup_errors.append(f"scratch database: {type(exc).__name__}")
        if fixture_inserted:
            try:
                _delete_fixture(source_engine, fixture_user)
            except Exception as exc:
                cleanup_errors.append(f"source fixture: {type(exc).__name__}")
        source_engine.dispose()
        admin_engine.dispose()
        if dump_path is not None:
            try:
                dump_path.unlink(missing_ok=True)
            except Exception as exc:
                cleanup_errors.append(f"temporary dump: {type(exc).__name__}")
        if cleanup_errors:
            message = "PostgreSQL restore-drill cleanup failed for " + ", ".join(cleanup_errors)
            if sys.exc_info()[0] is None:
                raise RuntimeError(message)
            print(f"warning: {message}", file=sys.stderr)


def assert_safe_project(name: str) -> None:
    if not SAFE_PROJECT_RE.fullmatch(name):
        raise ValueError("Compose project must use the scoped thoughtpins-* namespace")


def assert_safe_identifier(value: str, *, label: str) -> None:
    if not SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe {label}: {value!r}")


def _database_url(source: URL, database: str) -> URL:
    assert_safe_identifier(database, label="database name")
    return source.set(database=database)


def _compose_command(wsl_distro: str, project: str) -> list[str]:
    assert_safe_project(project)
    if not wsl_distro:
        return [shutil.which("docker") or "docker", "compose", "-p", project]
    if os.name != "nt":
        raise ValueError("--wsl-distro is supported only on Windows")
    if not SAFE_WSL_DISTRO_RE.fullmatch(wsl_distro):
        raise ValueError(f"Unsafe WSL distribution name: {wsl_distro!r}")
    return ["wsl.exe", "-d", wsl_distro, "-u", "root", "--", "docker", "compose", "-p", project]


def _run(command: list[str], *, stdin=None, stdout=None) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdin=stdin,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        tail = " | ".join(detail[-4:])[:600]
        raise RuntimeError(f"PostgreSQL backup command failed with exit code {completed.returncode}: {tail}")


def _insert_fixture(engine, user_id: str, entry_id: str, content_hash: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, display_name, api_key, is_active, is_admin, auth_method) "
                "VALUES (:id, 'Backup Drill', :api_key, true, false, 'api_key')"
            ),
            {"id": user_id, "api_key": f"backup-drill-{user_id}"},
        )
        conn.execute(
            text(
                "INSERT INTO raw_entries "
                "(id, user_id, raw_text, content_hash, source, processed_status) "
                "VALUES (:id, :user_id, 'PostgreSQL recovery fixture', :content_hash, 'recovery_drill', 'completed')"
            ),
            {"id": entry_id, "user_id": user_id, "content_hash": content_hash},
        )


def _delete_fixture(engine, user_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw_entries WHERE user_id = :user_id"), {"user_id": user_id})
        conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})


def _create_scratch_database(engine, database: str, owner: str) -> None:
    if not SAFE_SCRATCH_DATABASE_RE.fullmatch(database):
        raise ValueError("Scratch database escaped the recovery-drill namespace")
    assert_safe_identifier(owner, label="database owner")
    with engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{database}" OWNER "{owner}" TEMPLATE template0'))


def _drop_scratch_database(engine, database: str) -> None:
    if not SAFE_SCRATCH_DATABASE_RE.fullmatch(database):
        raise ValueError("Refusing to drop a database outside the recovery-drill namespace")
    with engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :database AND pid <> pg_backend_pid()"
            ),
            {"database": database},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))


def _database_snapshot(engine) -> DatabaseSnapshot:
    with engine.connect() as conn:
        tables = list(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            ).scalars()
        )
        rows: dict[str, int] = {}
        for table in tables:
            assert_safe_identifier(table, label="table name")
            rows[table] = int(conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())
        policies = [
            tuple(row)
            for row in conn.execute(
                text(
                    "SELECT tablename, policyname, permissive, roles::text, cmd, "
                    "coalesce(qual, ''), coalesce(with_check, '') "
                    "FROM pg_policies WHERE schemaname = 'public' "
                    "ORDER BY tablename, policyname"
                )
            )
        ]
        rls = [
            (str(row[0]), bool(row[1]), bool(row[2]))
            for row in conn.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname"
                )
            )
        ]
        alembic = list(conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars())
    return {"rows": rows, "policies": policies, "rls": rls, "alembic_versions": alembic}


def _snapshot_difference(source: DatabaseSnapshot, restored: DatabaseSnapshot) -> str:
    comparisons = (
        ("rows", source["rows"], restored["rows"]),
        ("policies", source["policies"], restored["policies"]),
        ("rls", source["rls"], restored["rls"]),
        ("alembic_versions", source["alembic_versions"], restored["alembic_versions"]),
    )
    changed = [name for name, source_value, restored_value in comparisons if source_value != restored_value]
    return "Restored PostgreSQL snapshot differs in: " + ", ".join(changed)


if __name__ == "__main__":
    raise SystemExit(main())
