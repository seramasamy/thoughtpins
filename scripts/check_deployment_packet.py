"""Validate the Thought Pins closed-beta deployment packet.

The packet is a non-secret deployment handoff. This checker keeps the runbook,
Compose rehearsal, production env template, domain plan, and store packet aligned.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "deploy" / "closed-beta-deployment-packet.json"
STORE_PACKET = ROOT / "deploy" / "store" / "submission-packet.json"

REQUIRED_SOURCE_FILES = {
    "production_env_template": ".env.production.example",
    "compose_rehearsal": "docker-compose.yml",
    "production_runbook": "docs/operations/PRODUCTION_RUNBOOK.md",
    "domain_plan": "deploy/DOMAIN_AND_DNS.md",
    "store_packet": "deploy/store/submission-packet.json",
    "review_notes": "deploy/store/review-notes-template.md",
}

REQUIRED_PUBLIC_HOSTS = {
    "marketing_site": "https://thoughtpins.com",
    "privacy_policy": "https://thoughtpins.com/privacy",
    "terms": "https://thoughtpins.com/terms",
    "support": "https://thoughtpins.com/support",
    "account_deletion": "https://thoughtpins.com/account/delete",
    "ai_disclosure": "https://thoughtpins.com/ai-disclosure",
    "web_app": "https://app.thoughtpins.com/app",
    "api": "https://api.thoughtpins.com/v1",
}

REQUIRED_STAGING_HOSTS = {
    "web_app": "https://staging.thoughtpins.com",
    "api": "https://api-staging.thoughtpins.com",
}

REQUIRED_RUNTIME_FLAGS = {
    "ENVIRONMENT": "production",
    "REQUIRE_API_AUTH": "true",
    "AUTO_CREATE_TABLES": "false",
    "ALLOW_USER_API_KEYS": "false",
    "RETURN_API_KEY_ON_REGISTER": "false",
    "RATE_LIMIT_ENABLED": "true",
    "PROCESS_ENTRIES_ASYNC": "true",
    "INGESTION_QUEUE_BACKEND": "celery",
    "VECTOR_MODE": "qdrant_remote",
    "EMBEDDING_PROVIDER": "openai",
    "METRICS_REQUIRE_AUTH": "true",
    "JSON_LOGS": "true",
    "SECURITY_HEADERS_ENABLED": "true",
    "RUN_STARTUP_RECOVERY": "false",
    "ENABLE_TELEGRAM_BOT": "false",
    "TELEGRAM_TEST_MODE": "false",
    "ENABLE_FOUNDER_MODE": "false",
    "SYSTEM_LOCKED": "true",
}

REQUIRED_VERIFICATION_COMMANDS = {
    "python scripts/release_check.py --skip-quality",
    "python scripts/check_deployment_packet.py",
    "python scripts/check_launch_packet.py",
    "python scripts/check_rls_static.py",
    "python scripts/check_host_capabilities.py",
    "python scripts/check_external_proof_artifacts.py --self-test",
    "python scripts/check_store_readiness_matrix.py --self-test",
    "python scripts/generate_store_readiness_matrix.py",
    "python scripts/generate_launch_packet.py",
    ".\\scripts\\run_compose_rehearsal.ps1",
    "DATABASE_URL=<migration-role-url> RLS_VERIFY_DATABASE_URL=<app-role-url> python scripts/verify_postgres_rls.py",
    ".\\scripts\\run_staging_smoke.ps1",
    "python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke",
    "python scripts/collect_closed_beta_evidence.py --api-base-url https://api-staging.thoughtpins.com --telegram-api --web-smoke",
}

SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
    re.compile(r"(?i)((?:api[_-]?key|auth[_-]?token|bot[_-]?token|password|jwt[_-]?secret)\s*[=:]\s*)[^\s,;'\"]+"),
    re.compile(r"(postgresql(?:\+psycopg2)?://)([^:@/]+):([^@/]+)@"),
    re.compile(r"(redis://)(:[^@/]+@)"),
]


def main() -> int:
    failures = run_checks()
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Deployment packet check failed: {len(failures)} failure(s).")
        return 1
    print("Deployment packet check passed.")
    return 0


def run_checks() -> list[str]:
    failures: list[str] = []
    packet = _load_json(PACKET, failures)
    store_packet = _load_json(STORE_PACKET, failures)
    if not packet or not store_packet:
        return failures

    _check_no_secrets(PACKET, failures)
    _check_basic(packet, failures)
    _check_sources(packet, failures)
    _check_hosts(packet, store_packet, failures)
    _check_processes(packet, failures)
    _check_services(packet, failures)
    _check_runtime_flags(packet, failures)
    _check_secret_handling(packet, failures)
    _check_verification_commands(packet, failures)
    _check_live_requirements(packet, failures)
    _check_repo_artifacts(packet, failures)
    _check_store_packet_reference(store_packet, failures)
    return failures


def _load_json(path: Path, failures: list[str]) -> dict:
    if not path.is_file():
        failures.append(f"Missing JSON file: {path.relative_to(ROOT)}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        failures.append(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}


def _check_no_secrets(path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append(f"{path.relative_to(ROOT)} appears to contain secret-like material")
    lowered = text.lower()
    for marker in ["todo", "tbd", "actual password", "sk-", "jina_", "fc-"]:
        if marker in lowered:
            failures.append(f"{path.relative_to(ROOT)} contains forbidden marker {marker!r}")


def _check_basic(packet: dict, failures: list[str]) -> None:
    if packet.get("app_name") != "Thought Pins":
        failures.append("deployment packet app_name must be Thought Pins")
    if packet.get("readiness_state") != "code_ready_pending_infrastructure_proof":
        failures.append("deployment packet readiness_state must be code_ready_pending_infrastructure_proof")
    if not str(packet.get("deployment_intent") or "").strip():
        failures.append("deployment packet must include deployment_intent")


def _check_sources(packet: dict, failures: list[str]) -> None:
    sources = packet.get("source_of_truth") or {}
    for key, relative in REQUIRED_SOURCE_FILES.items():
        if sources.get(key) != relative:
            failures.append(f"source_of_truth.{key} must be {relative}")
        if not (ROOT / relative).is_file():
            failures.append(f"source_of_truth.{key} points at missing file: {relative}")


def _check_hosts(packet: dict, store_packet: dict, failures: list[str]) -> None:
    hosts = packet.get("public_hosts") or {}
    for key, expected in REQUIRED_PUBLIC_HOSTS.items():
        actual = hosts.get(key)
        if actual != expected:
            failures.append(f"public_hosts.{key} must be {expected!r}, got {actual!r}")
        if actual and not _public_https(actual):
            failures.append(f"public_hosts.{key} must be public HTTPS")
        if (store_packet.get("public_urls") or {}).get(key) != expected:
            failures.append(f"store packet public_urls.{key} must match deployment packet")

    staging = packet.get("staging_hosts") or {}
    for key, expected in REQUIRED_STAGING_HOSTS.items():
        actual = staging.get(key)
        if actual != expected:
            failures.append(f"staging_hosts.{key} must be {expected!r}, got {actual!r}")
        if actual and not _public_https(actual):
            failures.append(f"staging_hosts.{key} must be public HTTPS")


def _check_processes(packet: dict, failures: list[str]) -> None:
    by_name = {item.get("name"): item for item in packet.get("runtime_processes") or []}
    expected = {
        "migrate": ("alembic upgrade head", "schema_owner", False),
        "api": ("python -m thoughtpins.server --api-only", "non_owner_app_role", True),
        "worker": ("python -m thoughtpins.worker", "non_owner_app_role", True),
    }
    for name, (command, role, service) in expected.items():
        item = by_name.get(name)
        if not item:
            failures.append(f"runtime_processes missing {name}")
            continue
        if item.get("command") != command:
            failures.append(f"runtime_processes.{name}.command must be {command}")
        if item.get("database_role") != role:
            failures.append(f"runtime_processes.{name}.database_role must be {role}")
        if item.get("runs_as_service") is not service:
            failures.append(f"runtime_processes.{name}.runs_as_service must be {service}")


def _check_services(packet: dict, failures: list[str]) -> None:
    services = packet.get("required_services") or {}
    postgres = services.get("postgres") or {}
    redis = services.get("redis") or {}
    vector = services.get("vector_store") or {}
    vault = services.get("vault_store") or {}
    reports = services.get("reports_store") or {}
    if (
        postgres.get("version") != "16"
        or postgres.get("rls_required") is not True
        or postgres.get("runtime_app_role") != "thoughtpins_app"
    ):
        failures.append("postgres service must require version 16, RLS, and thoughtpins_app runtime role")
    if redis.get("version") != "7" or "celery_broker" not in (redis.get("uses") or []):
        failures.append("redis service must require version 7 and celery_broker use")
    if (
        vector.get("mode") != "qdrant_remote"
        or vector.get("persistent_volume") != "thoughtpins-qdrant"
        or vector.get("authentication_required") is not True
    ):
        failures.append("vector_store must require qdrant_remote on thoughtpins-qdrant")
    if vault.get("persistent_volume") != "thoughtpins-vault" or vault.get("export_format") != "obsidian_vault":
        failures.append("vault_store must require thoughtpins-vault and obsidian_vault export")
    if reports.get("persistent_volume") != "thoughtpins-reports":
        failures.append("reports_store must require thoughtpins-reports")


def _check_runtime_flags(packet: dict, failures: list[str]) -> None:
    flags = packet.get("required_runtime_flags") or {}
    env = _parse_env(ROOT / ".env.production.example")
    for key, expected in REQUIRED_RUNTIME_FLAGS.items():
        if flags.get(key) != expected:
            failures.append(f"required_runtime_flags.{key} must be {expected}")
        if env.get(key) != expected:
            failures.append(f".env.production.example {key} must be {expected}")


def _check_secret_handling(packet: dict, failures: list[str]) -> None:
    handling = packet.get("secret_handling") or {}
    if handling.get("stored_in_repo") is not False:
        failures.append("secret_handling.stored_in_repo must be false")
    if handling.get("rotation_required_before_public_beta") is not True:
        failures.append("secret_handling.rotation_required_before_public_beta must be true")
    required = set(handling.get("required_external_secrets") or [])
    for key in [
        "API_KEY",
        "JWT_SECRET",
        "DATABASE_URL",
        "REDIS_URL",
        "DATA_ENCRYPTION_KEY",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "THOUGHTPINS_REVIEW_PASSWORD",
    ]:
        if key not in required:
            failures.append(f"secret_handling.required_external_secrets missing {key}")
    exports = set(handling.get("public_exports_must_pass") or [])
    for command in ["python scripts/forbidden_scan.py", "python scripts/check_public_export.py"]:
        if command not in exports:
            failures.append(f"secret_handling.public_exports_must_pass missing {command}")


def _check_verification_commands(packet: dict, failures: list[str]) -> None:
    commands = set(packet.get("verification_commands") or [])
    missing = REQUIRED_VERIFICATION_COMMANDS - commands
    if missing:
        failures.append(f"verification_commands missing: {sorted(missing)}")
    for command in commands:
        _check_command_target(command, failures)


def _check_command_target(command: str, failures: list[str]) -> None:
    if command.startswith("python "):
        parts = command.split()
        if len(parts) > 1 and parts[1].startswith("scripts/") and not (ROOT / parts[1]).is_file():
            failures.append(f"verification command references missing script: {parts[1]}")
    if command.startswith(".\\scripts\\"):
        script = command.split()[0].replace(".\\", "").replace("\\", "/")
        if not (ROOT / script).is_file():
            failures.append(f"verification command references missing script: {script}")
    if "verify_postgres_rls.py" in command and not (ROOT / "scripts" / "verify_postgres_rls.py").is_file():
        failures.append("RLS verification command references missing verifier")


def _check_live_requirements(packet: dict, failures: list[str]) -> None:
    reqs = packet.get("live_review_requirements") or {}
    for key in [
        "backend_live_during_review",
        "legal_pages_live_over_https",
        "review_account_seeded",
        "review_notes_sanitized",
        "maintenance_mode_documented",
        "native_submission_requires_native_shells",
    ]:
        if reqs.get(key) is not True:
            failures.append(f"live_review_requirements.{key} must be true")
    blockers = packet.get("known_external_blockers_before_closed_beta") or []
    if len(blockers) < 5:
        failures.append("known_external_blockers_before_closed_beta must list the real external tasks")


def _check_repo_artifacts(packet: dict, failures: list[str]) -> None:
    compose = _read("docker-compose.yml", failures)
    env = _read(".env.production.example", failures)
    runbook = _read("docs/operations/PRODUCTION_RUNBOOK.md", failures)
    domain = _read("deploy/DOMAIN_AND_DNS.md", failures)
    staging = _read("scripts/run_staging_smoke.ps1", failures)
    rehearsal = _read("scripts/run_compose_rehearsal.ps1", failures)
    rehearsal_py = _read("scripts/run_compose_rehearsal.py", failures)
    caddy = _read("deploy/Caddyfile.thoughtpins.example", failures)

    for marker in [
        "postgres:",
        "redis:",
        "qdrant:",
        "migrate:",
        "api:",
        "web:",
        "worker:",
        "thoughtpins_app",
        "python -m thoughtpins.worker",
        "python -m thoughtpins.web_proxy",
        "THOUGHTPINS_WEB_API_UPSTREAM",
        "thoughtpins-qdrant",
        "thoughtpins-vault",
    ]:
        if marker not in compose:
            failures.append(f"docker-compose.yml missing marker {marker}")
    for marker in [
        "PRIVACY_POLICY_URL=https://thoughtpins.com/privacy",
        "WEB_APP_URL=https://app.thoughtpins.com/app",
        "CORS_ALLOW_ORIGINS=https://app.thoughtpins.com",
    ]:
        if marker not in env:
            failures.append(f".env.production.example missing marker {marker}")
    for marker in [
        "run_compose_rehearsal.ps1",
        "run_compose_rehearsal.py",
        "check_rls_static.py",
        "verify_postgres_rls.py",
        "collect_local_closed_beta_evidence.py",
        "run_local_load_smoke.py",
        "run_local_cross_browser_audit.py",
        "GET /v1/health/deep",
    ]:
        if marker not in runbook:
            failures.append(f"docs/operations/PRODUCTION_RUNBOOK.md missing marker {marker}")
    for marker in [
        "app.thoughtpins.com",
        "api.thoughtpins.com",
        "staging.thoughtpins.com",
        "api-staging.thoughtpins.com",
    ]:
        if marker not in domain or marker not in caddy:
            failures.append(f"domain/reverse-proxy docs missing hostname {marker}")
    for marker in ["smoke_public_domain.py", "smoke_api.py", "k6-health.js", "k6-api-flow.js"]:
        if marker not in staging:
            failures.append(f"run_staging_smoke.ps1 missing marker {marker}")
    for marker in [
        "docker compose",
        "-p $ProjectName",
        "ProjectName",
        "Assert-SafeComposeProjectName",
        "teardown cannot target unrelated Compose projects",
        "compose-rehearsal",
        "production_parity_check.py",
        "--with-postgres-rls",
        "smoke_api.py",
        "smoke_restore_backup.py",
        "web smoke",
    ]:
        if marker not in rehearsal:
            failures.append(f"run_compose_rehearsal.ps1 missing marker {marker}")
    for marker in [
        "docker",
        "compose",
        "-p",
        "assert_safe_compose_project_name",
        "teardown cannot target unrelated Compose projects",
        "compose-rehearsal",
        "production_parity_check.py",
        "--with-postgres-rls",
        "smoke_api.py",
        "smoke_restore_backup.py",
        "web smoke",
    ]:
        if marker not in rehearsal_py:
            failures.append(f"run_compose_rehearsal.py missing marker {marker}")


def _check_store_packet_reference(store_packet: dict, failures: list[str]) -> None:
    if store_packet.get("deployment_packet") != "deploy/closed-beta-deployment-packet.json":
        failures.append("store submission packet must reference deploy/closed-beta-deployment-packet.json")
    commands = set(store_packet.get("evidence_commands") or [])
    if "python scripts/check_deployment_packet.py" not in commands:
        failures.append("store submission packet evidence_commands must include deployment packet checker")


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _read(relative: str, failures: list[str]) -> str:
    path = ROOT / relative
    if not path.is_file():
        failures.append(f"Missing file: {relative}")
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _public_https(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.hostname not in {"localhost", "127.0.0.1"}


if __name__ == "__main__":
    raise SystemExit(main())
