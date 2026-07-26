"""Offline release gate for Thought Pins.

This script intentionally avoids cloud or GitHub dependencies. It verifies the
source tree, API contract, migrations, frontend production build, and production
configuration shape. Optional flags can add Docker, PostgreSQL RLS, and running
API smoke checks when that infrastructure is available.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_STEP_TIMEOUT_SECONDS = 180


@dataclass
class CheckResult:
    name: str
    status: str
    seconds: float


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline Thought Pins release gate.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend production build.")
    parser.add_argument("--skip-quality", action="store_true", help="Skip optional lint/type/audit tooling checks.")
    parser.add_argument(
        "--strict-quality", action="store_true", help="Fail if ruff, mypy, pip-audit, or npm audit cannot run."
    )
    parser.add_argument("--with-docker", action="store_true", help="Run Docker Compose config validation.")
    parser.add_argument("--with-postgres-rls", action="store_true", help="Run scripts/verify_postgres_rls.py.")
    parser.add_argument("--api-base-url", help="Run scripts/smoke_api.py against this API base URL.")
    args = parser.parse_args()

    missing_modules = _missing_python_modules(
        include_tests=not args.skip_tests,
        include_quality=args.strict_quality and not args.skip_quality,
    )
    if missing_modules:
        print("Release gate preflight failed: the active Python environment is incomplete.")
        print(f"Missing modules: {', '.join(missing_modules)}")
        print("Create or activate .venv, then install the locked development environment with:")
        print(f'  "{_recommended_python_executable()}" -m pip install -e ".[dev]"')
        return 2

    results: list[CheckResult] = []

    def step(
        name: str,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path = ROOT,
        timeout: int = DEFAULT_STEP_TIMEOUT_SECONDS,
    ) -> bool:
        started = time.perf_counter()
        print(f"\n==> {name}")
        try:
            completed = subprocess.run(command, cwd=cwd, env=_with_src_pythonpath(env), timeout=timeout)
            returncode = completed.returncode
        except subprocess.TimeoutExpired:
            seconds = time.perf_counter() - started
            print(f"failed: timed out after {timeout}s")
            results.append(CheckResult(name, "timeout", seconds))
            return False
        seconds = time.perf_counter() - started
        status = "passed" if returncode == 0 else "failed"
        results.append(CheckResult(name, status, seconds))
        return returncode == 0

    def skip(name: str, reason: str, *, strict: bool = False) -> bool:
        print(f"\n==> {name}")
        print(f"{'failed' if strict else 'skipped'}: {reason}")
        results.append(CheckResult(name, "failed" if strict else "skipped", 0.0))
        return not strict

    ok = True
    py = sys.executable

    ok &= step("compile Python modules", [py, "-m", "compileall", "src", "tests", "scripts", "alembic"], timeout=60)
    ok &= step("architecture fitness", [py, "scripts/check_architecture_budget.py"], timeout=30)
    ok &= step("Python maintainability", [py, "scripts/check_python_maintainability.py"], timeout=150)
    ok &= step("Python dependency locks", [py, "scripts/check_dependency_locks.py"], timeout=60)
    ok &= step("container supply chain", [py, "scripts/check_container_supply_chain.py"], timeout=30)
    if not args.skip_tests:
        ok &= step(
            "pytest",
            [
                py,
                "scripts/run_pytest.py",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(_pytest_basetemp()),
            ],
            env=_test_check_env(),
            timeout=480,
        )
    ok &= step("OpenAPI contract", [py, "scripts/export_openapi.py", "--check"], timeout=60)
    ok &= step("forbidden reference and secret scan", [py, "scripts/forbidden_scan.py"], timeout=30)
    ok &= step("runtime log privacy", [py, "scripts/check_log_privacy.py"], timeout=30)
    ok &= step("public export hygiene", [py, "scripts/check_public_export.py"], timeout=60)
    ok &= step("workspace package hygiene", [py, "scripts/check_workspace_hygiene.py"], timeout=30)
    ok &= step("release dependency SBOM", [py, "scripts/generate_sbom.py"], timeout=180)
    ok &= step("domain readiness", [py, "scripts/check_domain_readiness.py"], timeout=30)
    ok &= step("app store compliance", [py, "scripts/app_store_compliance_check.py"], timeout=30)
    ok &= step("free initial release", [py, "scripts/check_free_launch.py"], timeout=30)
    ok &= step("app store approval tilt", [py, "scripts/check_app_store_approval_tilt.py"], timeout=30)
    ok &= step("store submission packet", [py, "scripts/check_store_submission_packet.py"], timeout=30)
    ok &= step("store readiness matrix", [py, "scripts/check_store_readiness_matrix.py", "--self-test"], timeout=30)
    ok &= step("review notes packet", [py, "scripts/check_review_notes_packet.py"], timeout=30)
    ok &= step("closed-beta deployment packet", [py, "scripts/check_deployment_packet.py"], timeout=30)
    ok &= step("closed-beta launch packet", [py, "scripts/check_launch_packet.py"], timeout=30)
    ok &= step("PostgreSQL RLS static coverage", [py, "scripts/check_rls_static.py"], timeout=30)
    ok &= step(
        "migration round-trip",
        [py, "scripts/check_migration_roundtrip.py"],
        timeout=90,
    )
    if not args.skip_frontend:
        ok &= _frontend_check(step)
    ok &= step("web review harness", [py, "scripts/check_web_review_harness.py"], timeout=30)
    ok &= step("web responsive layout", [py, "scripts/check_web_responsive_layout.py"], timeout=30)
    ok &= step("web accessibility contract", [py, "scripts/check_web_accessibility_contract.py"], timeout=30)
    ok &= step("web app product contract", [py, "scripts/check_web_app_contract.py"], timeout=30)
    ok &= step("PWA privacy and offline contract", [py, "scripts/check_pwa_contract.py"], timeout=30)
    ok &= step("production parity shape", [py, "scripts/production_parity_check.py"], timeout=90)
    ok &= step("host capability preflight", [py, "scripts/check_host_capabilities.py"], timeout=90)
    ok &= step(
        "external proof artifact verifier", [py, "scripts/check_external_proof_artifacts.py", "--self-test"], timeout=30
    )
    ok &= step("startup shutdown smoke", [py, "scripts/smoke_startup_shutdown.py"], timeout=90)
    ok &= step("mobile core scaffold", [py, "scripts/check_mobile_core.py"], timeout=30)
    ok &= step("iOS submission source", [py, "scripts/check_ios_submission_source.py"], timeout=30)
    ok &= step("native review handoff", [py, "scripts/check_native_review_handoff.py"], timeout=30)
    ok &= step(
        "memory infrastructure eval", [py, "scripts/evaluate_memory_infra.py"], env=_test_check_env(), timeout=60
    )
    if not args.skip_quality:
        ok &= _quality_checks(step, skip, py, strict=args.strict_quality)
    ok &= step("production config validation", [py, "scripts/validate_production.py"], env=_production_check_env())
    ok &= _alembic_sqlite_smoke(step, py)

    if args.with_docker:
        docker = shutil.which("docker")
        if not docker:
            print("\n==> Docker Compose config validation")
            print("failed: docker executable not found")
            ok &= skip("Docker Compose config validation", "docker executable not found", strict=True)
        else:
            ok &= step("Docker Compose config validation", [docker, "compose", "config"], timeout=60)

    if args.with_postgres_rls:
        ok &= step("PostgreSQL RLS verification", [py, "scripts/verify_postgres_rls.py"], timeout=180)

    if args.api_base_url:
        smoke_env = os.environ.copy()
        smoke_env["THOUGHTPINS_BASE_URL"] = args.api_base_url.rstrip("/")
        ok &= step("running API smoke test", [py, "scripts/smoke_api.py"], env=smoke_env, timeout=180)

    print("\nRelease gate summary:")
    for result in results:
        print(f"- {result.status:7} {result.seconds:6.1f}s  {result.name}")

    if ok:
        print("\nRelease gate passed.")
        return 0
    print("\nRelease gate failed.")
    return 1


def _frontend_check(step) -> bool:
    if not FRONTEND_DIR.exists():
        print("\n==> frontend production build")
        print("skipped: frontend directory is missing")
        return True
    npm = shutil.which("npm")
    if not npm:
        print("\n==> frontend production build")
        print("failed: npm executable not found")
        return False
    return step(
        "frontend production build",
        [npm, "run", "build"],
        cwd=FRONTEND_DIR,
        env=_npm_env("frontend-build"),
        timeout=120,
    )


def _quality_checks(step, skip, py: str, *, strict: bool) -> bool:
    ok = True
    if _module_available("ruff"):
        ok &= step(
            "ruff format",
            [py, "-m", "ruff", "format", "--check", "src", "tests", "scripts", "alembic"],
            timeout=60,
        )
        ok &= step("ruff lint", [py, "-m", "ruff", "check", "src", "tests", "scripts", "alembic"], timeout=60)
    else:
        ok &= skip("ruff lint", "ruff is not installed in the active Python environment", strict=strict)

    if _module_available("mypy"):
        ok &= step("mypy type check", [py, "-m", "mypy", "src/thoughtpins", "scripts"], timeout=180)
    else:
        ok &= skip("mypy type check", "mypy is not installed in the active Python environment", strict=strict)

    if _module_available("bandit"):
        ok &= step("Python security lint", [py, "-m", "bandit", "-r", "src/thoughtpins", "-ll"], timeout=120)
    else:
        ok &= skip("Python security lint", "bandit is not installed in the active Python environment", strict=strict)

    if _module_available("pip_audit"):
        ok &= step(
            "Python production dependency audit",
            [
                py,
                "-m",
                "pip_audit",
                "-r",
                "requirements-prod.lock",
                "--require-hashes",
                "--disable-pip",
                "--vulnerability-service",
                "osv",
                "--cache-dir",
                str(ROOT / ".tmp" / "pip-audit-cache"),
                "--progress-spinner",
                "off",
                "--timeout",
                "30",
            ],
            timeout=180,
        )
    else:
        ok &= skip(
            "Python dependency audit", "pip-audit is not installed in the active Python environment", strict=strict
        )

    npm = shutil.which("npm")
    package_lock = FRONTEND_DIR / "package-lock.json"
    if npm and package_lock.exists():
        ok &= step(
            "frontend dependency audit",
            [npm, "audit", "--audit-level=high"],
            cwd=FRONTEND_DIR,
            env=_npm_env("npm-audit"),
            timeout=180,
        )
    elif package_lock.exists():
        ok &= skip("frontend dependency audit", "npm executable not found", strict=strict)

    return ok


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _missing_python_modules(*, include_tests: bool, include_quality: bool) -> list[str]:
    required = {
        "alembic.config": "alembic",
        "loguru": "loguru",
        "radon": "radon",
        "sqlalchemy": "sqlalchemy",
        "uv": "uv",
        "vulture": "vulture",
    }
    if include_tests:
        required["pytest"] = "pytest"
    if include_quality:
        required.update(
            {
                "bandit": "bandit",
                "mypy": "mypy",
                "pip_audit": "pip-audit",
                "ruff": "ruff",
            }
        )
    return sorted(label for module, label in required.items() if not _module_available(module))


def _recommended_python_executable() -> Path | str:
    candidate = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return candidate if candidate.exists() else "python"


def _alembic_sqlite_smoke(step, py: str) -> bool:
    db_dir = ROOT / ".tmp" / "release-check"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / f"alembic-{secrets.token_hex(6)}.sqlite3"
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "development",
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "AUTO_CREATE_TABLES": "false",
            "REQUIRE_API_AUTH": "false",
            "TELEGRAM_TEST_MODE": "false",
            "ENABLE_FOUNDER_MODE": "false",
            "ENABLE_TELEGRAM_BOT": "false",
        }
    )
    try:
        return step("Alembic SQLite migration smoke", [py, "-m", "alembic", "upgrade", "head"], env=env, timeout=60)
    finally:
        db_path.unlink(missing_ok=True)


def _production_check_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "production",
            "API_VERSION": "1.0.0-rc.1",
            "PRIVACY_POLICY_URL": "https://thoughtpins.com/privacy",
            "TERMS_URL": "https://thoughtpins.com/terms",
            "SUPPORT_URL": "https://thoughtpins.com/support",
            "ACCOUNT_DELETION_URL": "https://thoughtpins.com/account/delete",
            "AI_DISCLOSURE_URL": "https://thoughtpins.com/ai-disclosure",
            "MIN_IOS_VERSION": "1.0.0",
            "MIN_ANDROID_VERSION": "1.0.0",
            "MIN_WEB_VERSION": "1.0.0",
            "RECOMMENDED_IOS_VERSION": "1.0.0",
            "RECOMMENDED_ANDROID_VERSION": "1.0.0",
            "RECOMMENDED_WEB_VERSION": "1.0.0",
            "IOS_STORE_URL": "https://apps.apple.com/app/id0000000000",
            "ANDROID_STORE_URL": "https://play.google.com/store/apps/details?id=com.thoughtpins.app",
            "WEB_APP_URL": "https://app.thoughtpins.com/app",
            "REQUIRE_API_AUTH": "true",
            "API_KEY": _fake_secret("api"),
            "JWT_SECRET": _fake_secret("jwt"),
            "ALLOW_USER_API_KEYS": "false",
            "RETURN_API_KEY_ON_REGISTER": "false",
            "GOOGLE_OAUTH_CLIENT_IDS": "",
            "APPLE_OAUTH_CLIENT_IDS": "",
            "VITE_GOOGLE_CLIENT_ID": "",
            "VITE_APPLE_CLIENT_ID": "",
            "AUTO_CREATE_TABLES": "false",
            "DATABASE_URL": "postgresql+psycopg2://thoughtpins_app:password@127.0.0.1:5432/thoughtpins",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "RATE_LIMIT_ENABLED": "true",
            "PROCESS_ENTRIES_ASYNC": "true",
            "INGESTION_QUEUE_BACKEND": "celery",
            "CELERY_BROKER_URL": "redis://127.0.0.1:6379/1",
            "CELERY_RESULT_BACKEND": "redis://127.0.0.1:6379/2",
            "LLM_PROVIDER": "openai_compatible",
            "LLM_API_KEY": _fake_secret("llm"),
            "EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": _fake_secret("openai"),
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
            "OPENAI_EMBEDDING_DIMENSIONS": "1536",
            "VECTOR_MODE": "qdrant_remote",
            "QDRANT_URL": "http://127.0.0.1:6333",
            "QDRANT_API_KEY": _fake_secret("qdrant"),
            "QDRANT_TIMEOUT_SECONDS": "10",
            "VECTOR_HEALTHCHECK_LIVE": "true",
            "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
            "SENTRY_DSN": "https://public@example.com/1",
            "SECURITY_HEADERS_ENABLED": "true",
            "RUN_STARTUP_RECOVERY": "false",
            "TELEGRAM_TEST_MODE": "false",
            "ENABLE_FOUNDER_MODE": "false",
            "ENABLE_TELEGRAM_BOT": "false",
        }
    )
    return env


def _test_check_env() -> dict[str, str]:
    """Keep offline tests independent from local live-provider .env settings."""
    env = os.environ.copy()
    test_tmp = ROOT / ".tmp"
    test_tmp.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "ENVIRONMENT": "development",
            "LLM_HEALTHCHECK_LIVE": "false",
            "VECTOR_HEALTHCHECK_LIVE": "false",
            "VECTOR_MODE": "memory",
            "EMBEDDING_PROVIDER": "local",
            "OPENAI_API_KEY": "",
            "PROCESS_ENTRIES_ASYNC": "false",
            "RUN_STARTUP_RECOVERY": "false",
            "ARTICLE_FETCH_PROVIDERS": "local",
            "LIBRARY_EXTRACT_GRAPH": "false",
            "TMP": str(test_tmp),
            "TEMP": str(test_tmp),
        }
    )
    return env


def _with_src_pythonpath(env: dict[str, str] | None = None) -> dict[str, str]:
    resolved = (env or os.environ.copy()).copy()
    src = str(ROOT / "src")
    current = resolved.get("PYTHONPATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if src not in parts:
        parts.insert(0, src)
    resolved["PYTHONPATH"] = os.pathsep.join(parts)
    return resolved


def _pytest_basetemp() -> Path:
    return ROOT / ".tmp" / f"pytest-basetemp-{secrets.token_hex(6)}"


def _npm_env(label: str) -> dict[str, str]:
    env = os.environ.copy()
    suffix = secrets.token_hex(6)
    npm_cache = ROOT / ".tmp" / f"npm-cache-{label}-{suffix}"
    npm_tmp = ROOT / ".tmp" / f"npm-tmp-{label}-{suffix}"
    npm_cache.mkdir(parents=True, exist_ok=True)
    npm_tmp.mkdir(parents=True, exist_ok=True)
    env["npm_config_cache"] = str(npm_cache)
    env["TMP"] = str(npm_tmp)
    env["TEMP"] = str(npm_tmp)
    if os.name == "nt":
        shim = "./scripts/vite-windows-net-use-shim.cjs"
        existing = env.get("NODE_OPTIONS", "").strip()
        env["NODE_OPTIONS"] = f"{existing} --require={shim}".strip()
    return env


def _fake_secret(prefix: str) -> str:
    return f"release-check-{prefix}-{secrets.token_urlsafe(32)}"


if __name__ == "__main__":
    raise SystemExit(main())
