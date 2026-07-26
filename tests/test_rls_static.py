import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_rls_static as rls_static  # noqa: E402


def test_static_rls_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_rls_static.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Static RLS coverage check passed." in result.stdout


def test_user_owned_tables_have_migration_and_live_verifier_coverage() -> None:
    user_tables = set(rls_static._metadata_user_tables())
    expected_rls_tables = user_tables - set(rls_static.RLS_EXEMPT_TABLES)

    assert expected_rls_tables <= rls_static._migration_rls_tables()
    assert rls_static._verifier_live_tables() == expected_rls_tables


def test_new_user_owned_tables_have_explicit_app_role_grants() -> None:
    user_tables = set(rls_static._metadata_user_tables())
    expected = rls_static._post_baseline_user_tables(user_tables)

    assert expected == {"llm_usage_events", "vault_import_sessions", "voice_assets"}
    assert expected <= rls_static._migration_explicit_app_role_tables()


def test_pre_tenant_auth_exemptions_are_explicit_and_narrow() -> None:
    assert set(rls_static.RLS_EXEMPT_TABLES) == {"auth_sessions", "oauth_credentials"}
    session_reason = rls_static.RLS_EXEMPT_TABLES["auth_sessions"].lower()
    oauth_reason = rls_static.RLS_EXEMPT_TABLES["oauth_credentials"].lower()
    assert "refresh-token" in session_reason or "refresh token" in session_reason
    assert "tenant context" in session_reason
    assert "hashed subject" in oauth_reason
    assert "tenant context" in oauth_reason
    assert {"auth_sessions", "oauth_credentials"} <= set(rls_static._metadata_user_tables())


def test_static_rls_check_is_in_release_and_handoff_paths() -> None:
    release_check = (ROOT / "scripts/release_check.py").read_text(encoding="utf-8-sig")
    parity_check = (ROOT / "scripts/production_parity_check.py").read_text(encoding="utf-8-sig")
    deployment_check = (ROOT / "scripts/check_deployment_packet.py").read_text(encoding="utf-8-sig")
    launch_check = (ROOT / "scripts/check_launch_packet.py").read_text(encoding="utf-8-sig")
    launch_generator = (ROOT / "scripts/generate_launch_packet.py").read_text(encoding="utf-8-sig")
    runbook = (ROOT / "docs/operations/PRODUCTION_RUNBOOK.md").read_text(encoding="utf-8-sig")
    packet = json.loads((ROOT / "deploy/closed-beta-deployment-packet.json").read_text(encoding="utf-8-sig"))

    marker = "python scripts/check_rls_static.py"
    assert "scripts/check_rls_static.py" in release_check
    assert "scripts/check_rls_static.py" in parity_check
    assert marker in deployment_check
    assert marker in launch_check
    assert marker in launch_generator
    assert marker in runbook
    assert marker in packet["verification_commands"]
