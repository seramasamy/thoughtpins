"""Static RLS coverage checks for Thought Pins PostgreSQL migrations.

This does not replace live PostgreSQL verification. It makes the offline release
gate fail if a user-owned table is added without tenant RLS migration coverage
or without inclusion in the live verifier.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
MIGRATIONS = ROOT / "alembic" / "versions"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_postgres_rls.py"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.db import Base  # noqa: E402

RLS_EXEMPT_TABLES = {
    "auth_sessions": "Refresh-token lookup happens before tenant context is known; application code filters by token hash and user state.",
    "oauth_credentials": "Provider-subject lookup happens before tenant context is known; routes use an exact hashed subject and expose no credential rows.",
}
REQUIRED_POLICY_MARKERS = (
    "NULLIF(current_setting('app.current_user_id', true), '')",
    "USING (user_id = {tenant_expr})",
    "WITH CHECK (user_id = {tenant_expr})",
)
EXPLICIT_APP_ROLE_GRANT_START = "0017_voice_archive.py"


def main() -> int:
    failures = run_checks()
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Static RLS coverage check failed: {len(failures)} failure(s).")
        return 1
    print("Static RLS coverage check passed.")
    return 0


def run_checks() -> list[str]:
    failures: list[str] = []
    user_tables = _metadata_user_tables()
    expected_rls = sorted(set(user_tables) - set(RLS_EXEMPT_TABLES))
    migration_text = _all_migration_text()
    migration_rls_tables = _migration_rls_tables()
    explicit_app_role_tables = _migration_explicit_app_role_tables()
    verifier_tables = _verifier_live_tables()

    missing_migration = sorted(set(expected_rls) - migration_rls_tables)
    if missing_migration:
        failures.append(f"RLS migrations missing user-owned tables: {missing_migration}")

    missing_verifier = sorted(set(expected_rls) - verifier_tables)
    if missing_verifier:
        failures.append(f"verify_postgres_rls.py LIVE_RLS_TABLES missing: {missing_verifier}")

    extra_verifier = sorted(verifier_tables - set(expected_rls))
    if extra_verifier:
        failures.append(f"verify_postgres_rls.py includes non-RLS tables: {extra_verifier}")

    post_baseline_tables = _post_baseline_user_tables(set(user_tables))
    missing_app_role_grants = sorted(post_baseline_tables - explicit_app_role_tables)
    if missing_app_role_grants:
        failures.append(f"Explicit app-role grants missing for new user-owned tables: {missing_app_role_grants}")

    for table in RLS_EXEMPT_TABLES:
        if table not in user_tables:
            failures.append(f"RLS exemption {table!r} does not match a user-owned metadata table")
    for required_exemption in ("auth_sessions", "oauth_credentials"):
        if required_exemption not in RLS_EXEMPT_TABLES:
            failures.append(f"{required_exemption} exemption must remain explicit and documented")

    for marker in REQUIRED_POLICY_MARKERS:
        if marker not in migration_text:
            failures.append(f"RLS migrations missing policy marker: {marker}")

    verify_text = VERIFY_SCRIPT.read_text(encoding="utf-8-sig", errors="ignore")
    for marker in [
        "RLS_EXEMPT_TABLES",
        "auth_sessions",
        "oauth_credentials",
        "PostgreSQL RLS verification passed for all user-owned RLS tables",
    ]:
        if marker not in verify_text:
            failures.append(f"verify_postgres_rls.py missing marker: {marker}")

    nullable = sorted(
        table.name for table in Base.metadata.tables.values() if "user_id" in table.c and table.c.user_id.nullable
    )
    allowed_nullable = {"audit_logs"}
    unexpected_nullable = sorted(set(nullable) - allowed_nullable)
    if unexpected_nullable:
        failures.append(f"Unexpected nullable user_id columns: {unexpected_nullable}")

    return failures


def _metadata_user_tables() -> list[str]:
    return sorted(table.name for table in Base.metadata.tables.values() if "user_id" in table.c)


def _all_migration_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8-sig", errors="ignore") for path in sorted(MIGRATIONS.glob("*.py")))


def _migration_rls_tables() -> set[str]:
    tables: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        module_lists = _string_list_assignments(text)
        for name, values in module_lists.items():
            if "RLS" in name:
                tables.update(values)
        tables.update(re.findall(r"ALTER TABLE ([A-Za-z0-9_]+) ENABLE ROW LEVEL SECURITY", text))
        tables.update(re.findall(r"_enable_rls\(\"([A-Za-z0-9_]+)\"\)", text))
    return tables


def _verifier_live_tables() -> set[str]:
    text = VERIFY_SCRIPT.read_text(encoding="utf-8-sig", errors="ignore")
    lists = _string_list_assignments(text)
    return set(lists.get("LIVE_RLS_TABLES", []))


def _migration_explicit_app_role_tables() -> set[str]:
    tables: set[str] = set()
    for path in _migrations_from_explicit_grant_start():
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        lists = _string_list_assignments(text)
        declared = set(lists.get("APP_ROLE_TABLES", []))
        if declared and (
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" not in text or "for table in APP_ROLE_TABLES" not in text
        ):
            continue
        tables.update(declared)
    return tables


def _post_baseline_user_tables(user_tables: set[str]) -> set[str]:
    created: set[str] = set()
    for path in _migrations_from_explicit_grant_start():
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        created.update(_created_table_names(text))
    return created & user_tables


def _created_table_names(text: str) -> set[str]:
    """Resolve literal and module-constant ``op.create_table`` names."""
    tree = ast.parse(text)
    constants: dict[str, str] = {}
    for node in tree.body:
        target: ast.Name | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target
            value = node.value
        if target and isinstance(value, ast.Constant) and isinstance(value.value, str):
            constants[target.id] = value.value

    tables: set[str] = set()
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Call) or not candidate.args:
            continue
        function = candidate.func
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "create_table"
            and isinstance(function.value, ast.Name)
            and function.value.id == "op"
        ):
            continue
        name_node = candidate.args[0]
        if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
            tables.add(name_node.value)
        elif isinstance(name_node, ast.Name) and name_node.id in constants:
            tables.add(constants[name_node.id])
    return tables


def _migrations_from_explicit_grant_start() -> list[Path]:
    migrations = sorted(MIGRATIONS.glob("*.py"))
    names = [path.name for path in migrations]
    if EXPLICIT_APP_ROLE_GRANT_START not in names:
        return []
    return migrations[names.index(EXPLICIT_APP_ROLE_GRANT_START) :]


def _string_list_assignments(text: str) -> dict[str, list[str]]:
    tree = ast.parse(text)
    values: dict[str, list[str]] = {}
    for node in tree.body:
        target_name = ""
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value
        else:
            continue
        if not target_name or value_node is None:
            continue
        if isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
            items: list[str] = []
            for item in value_node.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    items.append(item.value)
            if items:
                values[target_name] = items
    return values


if __name__ == "__main__":
    raise SystemExit(main())
