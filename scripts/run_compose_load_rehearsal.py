"""Run tenant-aware k6 traffic against a live production-shaped topology."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.orm import sessionmaker

from thoughtpins.auth import create_access_token
from thoughtpins.config import config
from thoughtpins.data_lifecycle import delete_user_data
from thoughtpins.db import IngestionJob, RawEntry, User
from thoughtpins.memory.vector_store import close_vector_store

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_K6 = ROOT / ".deps" / "k6-v2.0.0" / "bin" / "k6-v2.0.0-windows-amd64" / "k6.exe"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--base-url", default="http://127.0.0.1:8420")
    parser.add_argument("--jwt-secret", default="change-me-for-local-compose-jwt-secret-32chars")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--qdrant-api-key", default="change-me-for-local-compose-qdrant-key")
    parser.add_argument("--k6", type=Path, default=DEFAULT_K6)
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--iterations-per-user", type=int, default=2)
    parser.add_argument("--duration", default="20s")
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    parser.add_argument("--drain-timeout-seconds", type=int, default=600)
    parser.add_argument("--report-path", default="reports/load/compose-multi-tenant-current.json")
    args = parser.parse_args()
    _validate_args(args)

    engine = create_engine(args.database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    suffix = secrets.token_hex(4)
    users: list[User] = []
    accounts: list[dict[str, Any]] = []
    probe_job_ids: list[str] = []
    k6_summary = ROOT / "reports" / "load" / f"compose-multi-tenant-k6-{suffix}.json"
    k6_summary.parent.mkdir(parents=True, exist_ok=True)
    old_config = _configure_runtime(args)
    k6_returncode = 1
    k6_output = ""
    terminal_counts: dict[str, int] = {}
    cleanup_rows = -1
    error = ""
    started = time.perf_counter()

    try:
        with session_factory() as session:
            for index in range(args.users):
                marker = f"tp_probe_{suffix}_{index:02d}"
                probe_text = f"{marker}: tenant-isolation sentinel"
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                user = User(
                    id=f"load_{suffix}_{index:02d}",
                    email=f"load-{suffix}-{index:02d}@example.com",
                    display_name=f"Load Tenant {index:02d}",
                    api_key=secrets.token_urlsafe(24),
                    auth_method="password",
                    is_active=True,
                    is_admin=False,
                )
                entry = RawEntry(
                    id=secrets.token_hex(8),
                    user_id=user.id,
                    created_at_utc=now,
                    local_date=now.date(),
                    local_time=now.strftime("%H:%M:%S"),
                    source="load_probe",
                    raw_text=probe_text,
                    content_hash=hashlib.sha256(probe_text.encode("utf-8")).hexdigest(),
                    processed_status="completed",
                )
                probe_job = IngestionJob(
                    id=secrets.token_hex(8),
                    user_id=user.id,
                    status="completed",
                    source="load_probe",
                    dedup_key=f"load-probe:{suffix}:{index}",
                    raw_text=probe_text,
                    entry_id=entry.id,
                    created_at_utc=now,
                    queued_at_utc=now,
                    started_at_utc=now,
                    finished_at_utc=now,
                )
                session.add_all((user, entry, probe_job))
                users.append(user)
                probe_job_ids.append(probe_job.id)
            session.commit()
            for index, user in enumerate(users):
                accounts.append(
                    {
                        "index": index,
                        "marker": f"tp_probe_{suffix}_{index:02d}",
                        "probe_job_id": probe_job_ids[index],
                        "foreign_job_id": probe_job_ids[(index + 1) % len(probe_job_ids)],
                        "token": create_access_token(user),
                    }
                )

        env = os.environ.copy()
        env.update(
            {
                "BASE_URL": args.base_url.rstrip("/"),
                "VUS": str(args.users),
                "ITERATIONS_PER_VU": str(args.iterations_per_user),
                "MAX_DURATION": args.duration,
                "PAUSE_SECONDS": str(args.pause_seconds),
                "P95_MS": "1500",
                "REQUEST_TIMEOUT": "15s",
                "GRACEFUL_STOP": "15s",
                "LOAD_ACCOUNTS_JSON": json.dumps(accounts, separators=(",", ":")),
            }
        )
        completed = subprocess.run(
            [
                str(args.k6.resolve()),
                "run",
                "--quiet",
                "--summary-export",
                str(k6_summary),
                str(ROOT / "load" / "k6-multi-tenant-flow.js"),
            ],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_duration_seconds(args.duration) + 90,
        )
        k6_returncode = completed.returncode
        k6_output = _tail(completed.stdout + "\n" + completed.stderr)
        terminal_counts = _wait_for_jobs(session_factory, [user.id for user in users], args.drain_timeout_seconds)
        if k6_returncode != 0:
            error = "k6 thresholds failed"
        elif any(terminal_counts.get(status, 0) for status in ("failed", "dead_letter")):
            error = "one or more asynchronous jobs failed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        cleanup_rows = _cleanup_users(session_factory, [user.id for user in users])
        close_vector_store()
        _restore_runtime(old_config)
        engine.dispose()

    summary = _read_summary(k6_summary)
    report = {
        "schema_version": 1,
        "status": "passed" if not error else "failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "topology": "postgresql_redis_celery_qdrant",
        "production_capacity_proof": False,
        "users": args.users,
        "virtual_users": args.users,
        "duration": args.duration,
        "iterations_per_user": args.iterations_per_user,
        "pause_seconds": args.pause_seconds,
        "k6_returncode": k6_returncode,
        "metrics": summary,
        "job_statuses": terminal_counts,
        "tenant_rows_after_cleanup": cleanup_rows,
        "temporary_users_removed": cleanup_rows == 0,
        "seconds": round(time.perf_counter() - started, 3),
        "error": error or None,
        "k6_output_tail": k6_output,
    }
    report_path = Path(args.report_path)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({key: value for key, value in report.items() if key != "k6_output_tail"}, indent=2, sort_keys=True)
    )
    return 0 if report["status"] == "passed" and cleanup_rows == 0 else 1


def _validate_args(args: argparse.Namespace) -> None:
    if not args.database_url.startswith("postgresql"):
        raise ValueError("--database-url must identify PostgreSQL")
    if not args.k6.is_file():
        raise FileNotFoundError(f"k6 executable not found: {args.k6}")
    if not 2 <= args.users <= 100:
        raise ValueError("--users must be between 2 and 100")
    if not 1 <= args.iterations_per_user <= 10:
        raise ValueError("--iterations-per-user must be between 1 and 10")
    if not 1.0 <= args.pause_seconds <= 30.0:
        raise ValueError("--pause-seconds must be between 1 and 30")
    if not 30 <= args.drain_timeout_seconds <= 1800:
        raise ValueError("--drain-timeout-seconds must be between 30 and 1800")
    _duration_seconds(args.duration)


def _duration_seconds(value: str) -> int:
    suffix = value[-1:].lower()
    amount = float(value[:-1]) if suffix in {"s", "m"} else float(value)
    seconds = amount * 60 if suffix == "m" else amount
    if not 5 <= seconds <= 600:
        raise ValueError("duration must be between 5 seconds and 10 minutes")
    return int(seconds)


def _configure_runtime(args: argparse.Namespace) -> dict[str, Any]:
    values = {
        "JWT_SECRET": args.jwt_secret,
        "VECTOR_MODE": "qdrant_remote",
        "QDRANT_URL": args.qdrant_url,
        "QDRANT_API_KEY": args.qdrant_api_key,
    }
    previous = {name: getattr(config, name) for name in values}
    for name, value in values.items():
        setattr(config, name, value)
    return previous


def _restore_runtime(previous: dict[str, Any]) -> None:
    for name, value in previous.items():
        setattr(config, name, value)


def _wait_for_jobs(session_factory, user_ids: list[str], timeout_seconds: int) -> dict[str, int]:
    deadline = time.monotonic() + timeout_seconds
    statuses = ("pending", "retry", "queued", "running", "completed", "failed", "dead_letter", "cancelled")
    latest: dict[str, int] = {}
    while time.monotonic() < deadline:
        with session_factory() as session:
            rows = (
                session.query(IngestionJob.status, func.count(IngestionJob.id))
                .filter(IngestionJob.user_id.in_(user_ids))
                .group_by(IngestionJob.status)
                .all()
            )
        latest = {status: 0 for status in statuses}
        latest.update({str(status): int(count) for status, count in rows})
        if sum(latest[status] for status in ("pending", "retry", "queued", "running")) == 0:
            return latest
        time.sleep(2)
    raise TimeoutError(f"asynchronous job backlog did not drain: {latest}")


def _cleanup_users(session_factory, user_ids: list[str]) -> int:
    for user_id in user_ids:
        with session_factory() as session:
            delete_user_data(session, user_id)
            user = session.query(User).filter(User.id == user_id).first()
            if user is not None:
                session.delete(user)
                session.commit()
    with session_factory() as session:
        inspector = inspect(session.bind)
        total = 0
        for table in inspector.get_table_names(schema="public"):
            columns = {column["name"] for column in inspector.get_columns(table, schema="public")}
            if "user_id" not in columns:
                continue
            if not table.replace("_", "").isalnum():
                raise ValueError(f"Unsafe table name returned by PostgreSQL: {table!r}")
            total += int(
                session.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE user_id = ANY(:user_ids)'),
                    {"user_ids": user_ids},
                ).scalar_one()
            )
        total += int(session.query(func.count(User.id)).filter(User.id.in_(user_ids)).scalar() or 0)
    return total


def _read_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("metrics") or {}
    duration = metrics.get("http_req_duration") or {}
    failed = metrics.get("http_req_failed") or {}
    checks = metrics.get("checks") or {}
    requests = metrics.get("http_reqs") or {}
    iterations = metrics.get("iterations") or {}
    return {
        "http_requests": int(requests.get("count") or 0),
        "iterations": int(iterations.get("count") or 0),
        "p95_ms": round(float(duration.get("p(95)") or 0.0), 3),
        "max_ms": round(float(duration.get("max") or 0.0), 3),
        "failed_rate": round(float(failed.get("value") or 0.0), 6),
        "checks_passed": int(checks.get("passes") or 0),
        "checks_failed": int(checks.get("fails") or 0),
    }


def _tail(value: str, lines: int = 60) -> str:
    return "\n".join((value or "").splitlines()[-lines:])


if __name__ == "__main__":
    raise SystemExit(main())
