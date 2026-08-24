"""Local production-parity checks that do not require cloud access.

The script validates that the repo can run with the production-shaped stack:
PostgreSQL, Redis, Alembic, a separate API process, a separate web surface, and a separate worker. It
does not start or stop services. If Docker or a live API is unavailable, those
checks are reported as skipped unless the corresponding strict flag is used.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local production parity.")
    parser.add_argument("--base-url", default=os.getenv("THOUGHTPINS_BASE_URL", ""), help="Running API base URL.")
    parser.add_argument(
        "--api-key",
        default=os.getenv("THOUGHTPINS_API_KEY", ""),
        help="Optional API credential for protected deep-health checks.",
    )
    parser.add_argument("--strict-docker", action="store_true", help="Fail when Docker is unavailable.")
    parser.add_argument("--strict-api", action="store_true", help="Fail when --base-url is absent or unhealthy.")
    parser.add_argument("--with-postgres-rls", action="store_true", help="Run scripts/verify_postgres_rls.py.")
    args = parser.parse_args()

    checks: list[Check] = []
    checks.extend(_check_compose_shape())
    checks.extend(_check_docker_config(strict=args.strict_docker))
    checks.extend(_check_migration_shape())
    checks.append(_run_static_rls())
    checks.extend(_check_live_api(args.base_url, strict=args.strict_api, api_key=args.api_key))
    if args.with_postgres_rls:
        checks.append(_run_postgres_rls())
    else:
        checks.append(Check("PostgreSQL RLS live verification", "skipped", "pass --with-postgres-rls with DB URLs set"))

    for check in checks:
        suffix = f" - {check.detail}" if check.detail else ""
        print(f"{check.status.upper():7} {check.name}{suffix}")
    ok = all(check.status in {"passed", "skipped"} for check in checks)
    return 0 if ok else 1


def _check_compose_shape() -> list[Check]:
    path = ROOT / "docker-compose.yml"
    if not path.exists():
        return [Check("Docker Compose file", "failed", "docker-compose.yml missing")]
    text = path.read_text(encoding="utf-8")
    required = {"postgres", "redis", "qdrant", "migrate", "api", "web", "worker"}
    services_text = text.split("\nvolumes:", 1)[0]
    services = set(re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):\s*$", services_text))
    checks = [
        Check(
            "Docker Compose services",
            "passed" if required <= services else "failed",
            f"found={','.join(sorted(services))}",
        )
    ]
    postgres_text = _service_block(text, "postgres")
    qdrant_text = _service_block(text, "qdrant")
    migrate_text = _service_block(text, "migrate")
    api_text = _service_block(text, "api")
    web_text = _service_block(text, "web")
    worker_text = _service_block(text, "worker")
    migrate_env = _env_map_from_block(migrate_text)
    api_env = _env_map_from_block(api_text)
    worker_env = _env_map_from_block(worker_text)
    checks.append(
        _expect_block_contains(
            "Postgres app-role init script", postgres_text, "./deploy/postgres/init:/docker-entrypoint-initdb.d:ro"
        )
    )
    checks.append(_expect_env("Migration PostgreSQL owner URL", migrate_env, "DATABASE_URL", "postgresql+psycopg2://"))
    checks.append(_expect_env("Migration app role target", migrate_env, "THOUGHTPINS_APP_DB_ROLE", "thoughtpins_app"))
    checks.append(_expect_block_contains("Separate migration command", migrate_text, "alembic upgrade head"))
    checks.append(_expect_env("API PostgreSQL URL", api_env, "DATABASE_URL", "postgresql+psycopg2://"))
    checks.append(_expect_env_contains("API uses non-owner app role", api_env, "DATABASE_URL", "thoughtpins_app:"))
    checks.append(_expect_env("API Redis URL", api_env, "REDIS_URL", "redis://"))
    checks.append(_expect_env("API async queue", api_env, "INGESTION_QUEUE_BACKEND", "celery"))
    checks.append(_expect_env("API shared vector store", api_env, "VECTOR_MODE", "qdrant_remote"))
    checks.append(_expect_env("API vector endpoint", api_env, "QDRANT_URL", "http://qdrant:6333"))
    checks.append(_expect_block_contains("API vector authentication", api_text, "QDRANT_API_KEY:"))
    checks.append(_expect_env("API hosted embeddings", api_env, "EMBEDDING_PROVIDER", "openai"))
    checks.append(_expect_env_contains("API hosted transcription", api_env, "TRANSCRIPTION_PROVIDER", "hosted"))
    checks.append(
        _expect_env_contains(
            "API transcription credential fallback",
            api_env,
            "TRANSCRIPTION_API_KEY",
            "OPENAI_API_KEY",
        )
    )
    web_env = _env_map_from_block(web_text)
    checks.append(_expect_env("Web API upstream", web_env, "THOUGHTPINS_WEB_API_UPSTREAM", "http://api:8420"))
    checks.append(_expect_block_contains("Separate web command", web_text, "python -m thoughtpins.web_proxy"))
    checks.append(_expect_block_contains("Web healthcheck", web_text, "http://127.0.0.1:8421/health"))
    checks.append(_expect_env("Worker PostgreSQL URL", worker_env, "DATABASE_URL", "postgresql+psycopg2://"))
    checks.append(
        _expect_env_contains("Worker uses non-owner app role", worker_env, "DATABASE_URL", "thoughtpins_app:")
    )
    checks.append(_expect_env("Worker Redis broker", worker_env, "CELERY_BROKER_URL", "redis://"))
    checks.append(_expect_env("Worker shared vector store", worker_env, "VECTOR_MODE", "qdrant_remote"))
    checks.append(_expect_env("Worker vector endpoint", worker_env, "QDRANT_URL", "http://qdrant:6333"))
    checks.append(_expect_block_contains("Worker vector authentication", worker_text, "QDRANT_API_KEY:"))
    checks.append(_expect_env("Worker hosted embeddings", worker_env, "EMBEDDING_PROVIDER", "openai"))
    checks.append(_expect_env_contains("Worker hosted transcription", worker_env, "TRANSCRIPTION_PROVIDER", "hosted"))
    checks.append(
        _expect_env_contains(
            "Worker transcription credential fallback",
            worker_env,
            "TRANSCRIPTION_API_KEY",
            "OPENAI_API_KEY",
        )
    )
    worker_command = "\n".join(
        line.strip() for line in worker_text.splitlines() if "command:" in line or "thoughtpins.worker" in line
    )
    checks.append(
        Check(
            "Separate worker command",
            "passed" if "thoughtpins.worker" in worker_command else "failed",
            worker_command,
        )
    )
    checks.append(_expect_block_contains("Worker process healthcheck", worker_text, "os.kill(1, 0)"))
    checks.append(_expect_block_contains("Worker broker healthcheck", worker_text, "CELERY_BROKER_URL"))
    checks.append(_expect_block_contains("Qdrant persisted storage", qdrant_text, "thoughtpins-qdrant:/qdrant/storage"))
    checks.append(_expect_block_contains("Qdrant healthcheck", qdrant_text, "/dev/tcp/127.0.0.1/6333"))
    checks.append(_expect_block_contains("API persisted vault volume", api_text, "thoughtpins-vault:/app/vault"))
    checks.append(_expect_block_contains("Worker persisted vault volume", worker_text, "thoughtpins-vault:/app/vault"))
    checks.append(_expect_compose_contains(text, "Declared vector volume", "thoughtpins-qdrant:"))
    checks.append(_expect_compose_contains(text, "Declared vault volume", "thoughtpins-vault:"))
    checks.extend(_check_web_serving_shape())
    return checks


def _check_web_serving_shape() -> list[Check]:
    dockerfile = ROOT / "Dockerfile"
    public_routes = ROOT / "src" / "thoughtpins" / "api_routes" / "public.py"
    docker_text = dockerfile.read_text(encoding="utf-8") if dockerfile.exists() else ""
    routes_text = public_routes.read_text(encoding="utf-8") if public_routes.exists() else ""
    return [
        Check(
            "Web build copied into runtime image",
            "passed" if "COPY --from=web /web/dist ./frontend/dist" in docker_text else "failed",
            "API image must contain the React build for closed-beta web review",
        ),
        Check(
            "Web app route served by API",
            "passed"
            if '@page_route("/app"' in routes_text and 'Path("frontend") / "dist"' in routes_text
            else "failed",
            "/app should serve the built client from the API origin",
        ),
        Check(
            "Public site copied into runtime image",
            "passed" if "COPY site ./site" in docker_text else "failed",
            "API image must contain reviewed privacy, support, AI disclosure, and account deletion pages",
        ),
        Check(
            "Static public legal pages served by API",
            "passed"
            if "_resolve_site_dir" in routes_text and '@page_route("/assets/{path:path}")' in routes_text
            else "failed",
            "API/app origin should serve the same public legal pages and assets as thoughtpins.com when packaged",
        ),
        Check(
            "Dedicated web proxy module",
            "passed" if (ROOT / "src" / "thoughtpins" / "web_proxy.py").is_file() else "failed",
            "Compose web service should serve /app and proxy /v1",
        ),
    ]


def _check_docker_config(*, strict: bool) -> list[Check]:
    docker = shutil.which("docker")
    if not docker:
        return [Check("Docker Compose config", "failed" if strict else "skipped", "docker executable not found")]
    completed = subprocess.run([docker, "compose", "config"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    status = "passed" if completed.returncode == 0 else "failed"
    detail = "config valid" if completed.returncode == 0 else (completed.stderr or completed.stdout)[-500:]
    return [Check("Docker Compose config", status, detail)]


def _check_migration_shape() -> list[Check]:
    versions = sorted((ROOT / "alembic" / "versions").glob("*.py"))
    names = [path.name for path in versions]
    checks = [
        Check("Alembic versioned migrations", "passed" if len(versions) >= 8 else "failed", f"{len(versions)} files"),
        Check(
            "RLS migration present",
            "passed" if any("rls" in name.lower() for name in names) else "failed",
            ", ".join(names),
        ),
        Check(
            "PostgreSQL app-role grant migration present",
            "passed" if any("app_role_grants" in name.lower() for name in names) else "failed",
            ", ".join(names),
        ),
        Check(
            "PostgreSQL RLS verifier script",
            "passed" if (ROOT / "scripts" / "verify_postgres_rls.py").exists() else "failed",
        ),
    ]
    return checks


def _check_live_api(base_url: str, *, strict: bool, api_key: str = "") -> list[Check]:
    if not base_url:
        return [Check("Live API deep health", "failed" if strict else "skipped", "no --base-url provided")]
    base_url = base_url.rstrip("/")
    try:
        headers = {"X-API-Key": api_key} if api_key else None
        response = httpx.get(f"{base_url}/v1/health/deep", headers=headers, timeout=15)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        return [Check("Live API deep health", "failed", str(exc))]
    checks = body.get("checks") or {}
    llm = checks.get("llm") or {}
    vector = checks.get("vector") or {}
    jobs = checks.get("jobs") or {}
    worker = checks.get("worker") or {}
    backlog = sum(int(jobs.get(key) or 0) for key in ("pending", "retry", "running"))
    return [
        Check("Live API deep health", "passed" if body.get("status") == "ok" else "failed", str(body.get("status"))),
        Check(
            "Live AI processing",
            "passed"
            if llm.get("configured")
            and llm.get("status") in {"ok", "configured"}
            and "model" not in llm
            and "provider" not in llm
            else "failed",
            str(llm),
        ),
        Check(
            "Live memory search",
            "passed" if vector.get("status") in {"ok", "configured"} and "embedding_model" not in vector else "failed",
            str(vector),
        ),
        Check("Live worker", "passed" if worker.get("status") in {"ok", "configured"} else "failed", str(worker)),
        Check("Live job backlog", "passed" if backlog == 0 else "failed", str(jobs)),
    ]


def _run_postgres_rls() -> Check:
    completed = subprocess.run([sys.executable, "scripts/verify_postgres_rls.py"], cwd=ROOT, text=True, timeout=180)
    return Check(
        "PostgreSQL RLS live verification",
        "passed" if completed.returncode == 0 else "failed",
        "verify_postgres_rls.py",
    )


def _run_static_rls() -> Check:
    completed = subprocess.run(
        [sys.executable, "scripts/check_rls_static.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = (completed.stdout or completed.stderr or "check_rls_static.py").strip().splitlines()
    detail = output[-1] if output else "check_rls_static.py"
    return Check(
        "PostgreSQL RLS static coverage",
        "passed" if completed.returncode == 0 else "failed",
        detail,
    )


def _service_block(text: str, service_name: str) -> str:
    pattern = re.compile(rf"(?ms)^  {re.escape(service_name)}:\s*\n(.*?)(?=^  [a-zA-Z0-9_-]+:\s*$|^volumes:\s*$|\Z)")
    match = pattern.search(text)
    return match.group(1) if match else ""


def _env_map_from_block(block: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z0-9_]+", key):
            continue
        parsed[key] = value.strip().strip('"').strip("'")
    return parsed


def _expect_block_contains(name: str, block: str, needle: str) -> Check:
    return Check(name, "passed" if needle in block else "failed", needle)


def _expect_compose_contains(text: str, name: str, needle: str) -> Check:
    return Check(name, "passed" if needle in text else "failed", needle)


def _expect_env_contains(name: str, env: dict[str, str], key: str, expected_fragment: str) -> Check:
    value = env.get(key, "")
    return Check(name, "passed" if expected_fragment in value else "failed", f"{key}={_redact(value)}")


def _expect_env(name: str, env: dict[str, str], key: str, expected_prefix_or_value: str) -> Check:
    value = env.get(key, "")
    if expected_prefix_or_value.endswith("://"):
        ok = value.startswith(expected_prefix_or_value)
    else:
        ok = value == expected_prefix_or_value
    return Check(name, "passed" if ok else "failed", f"{key}={_redact(value)}")


def _redact(value: str) -> str:
    if not value:
        return ""
    if "@" in value and "://" in value:
        scheme, rest = value.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[-1]}"
    if len(value) > 48:
        return value[:16] + "...redacted"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
