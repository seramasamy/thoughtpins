# Migrations

26 revisions in `versions/`, applied with Alembic. Production databases are
migrated; they are never created by `AUTO_CREATE_TABLES`, which
`validate_startup` refuses outside local development.

```bash
alembic upgrade head
alembic revision -m "what changed"
```

`scripts/check_migration_roundtrip.py` runs in the release gate and applies every
revision forward against SQLite from empty, so a broken chain fails before it
reaches a real database.

## Two things to know before adding one

**Row-level security is part of the schema, not the application.** Tenant tables
carry `FORCE ROW LEVEL SECURITY` and their policies live in these revisions
(`0002_postgres_rls_policies`, `0004_audit_log_rls`, `0009_postgres_app_role_grants`).
A new tenant-owned table needs its policy in the same revision that creates it —
`scripts/check_rls_static.py` fails the build otherwise, and the guarantee is
enforced by the database rather than by every query remembering a `WHERE`.

**`src/thoughtpins/migrations/frozen_initial_schema.py` is a snapshot, not a
migration.** It records the initial shape for comparison. Changing a column name
means changing it there too, which is why renames cost more than they look —
`telegram_message_id` is still called that on `raw_entries` even though the web
path writes a web message id into it, because the rename reaches the frozen
schema, ingestion, corrections, and startup recovery to fix a name.
