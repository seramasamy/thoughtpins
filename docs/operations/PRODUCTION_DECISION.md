# Production Decision

## Recommendation

Thought Pins is ready as a local founder build and can be used as a shared-team
backend after PostgreSQL deployment verification. It is not ready for public
consumer production until external workers, OAuth if needed, operational
monitoring, and load/security gates are in place.

## Supported Modes

### Local Founder Mode

Use this for Telegram testing and personal journaling.

- SQLite is acceptable.
- `TELEGRAM_TEST_MODE=true` may be used to claim the first Telegram user.
- `ENABLE_FOUNDER_MODE=true` exposes the `/founder` command and founder test
  personality.
- This mode is blocked in `ENVIRONMENT=production`.

### Shared Backend Mode

Use this for a small controlled group.

- PostgreSQL and Redis are required.
- JWT auth, refresh-token rotation, rate limiting, and account export/delete are
  available.
- Celery worker mode is available for async extraction and should be used in any
  multi-instance deployment.
- Google/Apple OAuth ID-token verification is available when provider client IDs
  are configured.
- Request IDs, error envelopes, metrics, and deep health checks are available.
- App-level tenant filters are implemented.
- Alembic migration `0002_postgres_rls_policies` adds PostgreSQL RLS policies for
  journal-owned tables.
- Run `python scripts/validate_production.py` before deploy.

### Public Consumer Production

Do not launch publicly until these are complete:

- Verify RLS with the exact non-owner production database role.
- Run the Celery worker path under load with the production Redis broker.
- Configure Apple/Google OAuth client IDs if mobile consumer login requires it.
- Add endpoint-by-endpoint tenant-isolation tests for every read/export path.
- Add coverage thresholds, backup/restore drills, uptime monitoring, and log
  redaction review.

## Current Architecture Choice

Keep the core memory layer as a FastAPI/PostgreSQL service with Redis for rate
limits/cache and a queue backend for extraction workers. Telegram remains an
optional adapter, not the product core.
