# Thought Pins Production Plan

This plan tracks the gap between the current backend and a production-grade
multi-user product.

## Current State After Hardening Pass

Implemented in this repository:

- Package imports normalized to `thoughtpins`.
- `/v1` API routes added while preserving the main legacy route aliases.
- Data API authentication via JWT bearer tokens, API-key bootstrap, and
  per-user API keys.
- Password registration/login, refresh-token rotation, and logout/session
  revocation.
- User-scoped ownership columns added across journal-derived tables.
- Ingestion populates `user_id`; API reads use user-scoped stores.
- Async ingestion jobs with status tracking and startup recovery for pending or
  stale jobs.
- Alembic scaffolding with a baseline migration.
- Redis-backed rate limiting with in-memory fallback.
- Account export and deletion lifecycle endpoints.
- Docker Compose for PostgreSQL, Redis, and the API.
- Celery worker backend for production async extraction.
- Request IDs, consistent error envelopes, metrics, and worker health checks.
- OAuth ID-token verification for Apple and Google.
- Focused tests for auth, tenant stats, entries, export/delete, jobs, OAuth,
  email verification, and Telegram modes.
- Local-only Telegram founder/test mode with first-user allowlisting and a
  founder personality profile.
- PostgreSQL RLS migration artifact for journal-owned tables.
- Audit logs for auth, entry, job, and account lifecycle events, included in
  export/delete and protected by PostgreSQL RLS.
- Security headers, request body limits, and endpoint-specific rate limits.
- Job list, retry, and cancel endpoints for mobile/web processing UX.
- Backend deploy templates, OpenAPI export check, Docker build CI job, and
  black-box API smoke/load scripts.
- Hard-coded Telegram token and private user defaults removed from config.
- Telegram bot is optional and disabled unless explicitly configured.
- Production personality registry reduced to `friendly`, `clear`, and `mirror`.
- JSON logging and optional Sentry initialization are configured.
- Deep health endpoint checks database, Redis, worker heartbeat, job backlog,
  vector storage configuration, and configured LLM provider status. Live LLM/vector
  checks are opt-in so health probes do not burn tokens by default.

This is a robust local/shared-team backend foundation, not yet a horizontally
scaled consumer production backend.

## Production Blockers

| Priority | Item | Current State | Production Need |
| --- | --- | --- | --- |
| Critical | Database | SQLite default; PostgreSQL URL and Compose path supported through sync SQLAlchemy | Production PostgreSQL deploy, backup/restore, read-replica path, migration tests |
| Critical | Migrations | Alembic baseline exists; `create_all()` limited to local development | Migration CI against PostgreSQL and a real schema-diff review process |
| Critical | Auth | Password login, JWT access tokens, refresh rotation, API-key bootstrap | OAuth Apple/Google if required by product, session/device management UX |
| Critical | Tenant isolation | App-level `user_id` filters and focused tests | PostgreSQL row-level security and endpoint-by-endpoint isolation coverage |
| Critical | Async extraction | Celery worker backend plus local thread fallback; durable DB status and dead-letter handling | Load-test worker throughput and tune retries/queues |
| High | Rate limiting | Redis-backed limiter with memory fallback and endpoint-specific tiers | Abuse dashboards and adaptive limits |
| High | Monitoring | Loguru JSON mode and optional Sentry config | Sentry enabled in deploy, alerting, uptime checks, logs shipped to aggregation |
| High | Config | Env-driven config with production validation | Secrets manager integration and per-environment deployment manifests |
| High | API docs | FastAPI OpenAPI plus examples, global error envelope, and `/v1/errors` catalog | SDK contract and deprecation policy |
| High | Health checks | Light and deep health endpoints cover DB, Redis, worker, jobs, vector, and configured LLM provider status | Enable live LLM/vector checks in staging if desired |
| Medium | Tests | Focused tests for auth, user scope, jobs, and export/delete | Broader suite: ingestion edges, entities, reports, search, failure paths |
| Medium | CI/CD | CI covers compile, OpenAPI export, lint, type check, tests, migration smoke, forbidden scan, pip-audit, PostgreSQL RLS, and Docker build | Deployment pipeline and coverage threshold |
| Medium | Caching | None | Redis cache for navigational map, entity index, and common search queries |
| Medium | GDPR | Account export/delete endpoints include user audit logs | Retention policy, audit policy, deletion SLA, legal copy |
| Polish | Telegram adapter | Optional legacy adapter | Keep as plugin/adapter; app product should not depend on it |
| Polish | Load testing | None | k6 or Locust baseline and regression thresholds |

## Recommended Build Order

1. Finish PostgreSQL hardening
   - Run the current Alembic migrations in CI against PostgreSQL.
   - Verify RLS policies with the exact non-owner production app role.
   - Keep migration/table-owner and app runtime database roles separate.
   - Add backup/restore and migration rollback smoke tests.

2. Exercise production worker path
   - Run Celery worker under realistic LLM latency and failure modes.
   - Tune retry policy, queue concurrency, and dead-letter review workflow.
   - Add notification/callback path for completed processing if the client needs it.

3. API contract and validation
   - Expand Pydantic request/response schemas.
   - Add consistent error envelope.
   - Add pagination, sorting, and limits on list endpoints.

4. Rate limiting and caching
   - Split rate-limit tiers by endpoint cost.
   - Cache user-specific navigational maps and entity indexes.

5. Compliance and data lifecycle
   - Add retention and audit-log policy.
   - Add human-readable export manifests and deletion receipts.

6. Quality gate
   - Add coverage threshold, dependency scanning, and load tests.
   - Define deployment checklist and rollback procedure.

## Launch Standard

Do not launch multi-user production until these are true:

- Every data query has an automated tenant-isolation test.
- App-level user filters are backed by PostgreSQL RLS.
- Migrations are the only schema-change path outside local development.
- Entry ingestion runs through Celery/Redis in production.
- Auth uses short-lived access tokens and refresh-token rotation.
- Logs and error monitoring avoid raw journal contents.
