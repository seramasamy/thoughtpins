# Backend Release Checklist

Use this before tagging a backend release.

## One Command

- `python scripts/release_check.py`
- Strict local quality gate when PyPI tools are installed:
  `python scripts/release_check.py --strict-quality`
- Full infrastructure gate when Docker/PostgreSQL are available:
  `python scripts/release_check.py --strict-quality --with-docker --with-postgres-rls`
- Redacted closed-beta evidence packet:
  `python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke`
  or against an existing API: `python scripts/collect_closed_beta_evidence.py --web-smoke`

Bootstrap a fresh local machine:

```powershell
.\scripts\bootstrap_local.ps1
```

## Local

- `python -m compileall src tests scripts alembic`
- `python -m pytest`
- `alembic upgrade head` against a fresh SQLite smoke DB
- `python scripts/export_openapi.py --check`
- `python scripts/forbidden_scan.py`
- `python scripts/check_store_submission_packet.py` validates `deploy/store/submission-packet.json`, `deploy/store/store-policy-requirements.json`, and the review notes reference
- `python scripts/check_review_notes_packet.py` validates `deploy/store/review-notes-template.md` has no secrets/placeholders and matches the store packet
- `python scripts/check_deployment_packet.py` validates `deploy/closed-beta-deployment-packet.json`, deploy hosts, runtime flags, services, and proof commands
- `python scripts/check_web_app_contract.py`
- `python scripts/smoke_startup_shutdown.py`
- `python scripts/collect_local_closed_beta_evidence.py`
- `python scripts/check_mobile_core.py`
- `python scripts/check_native_review_handoff.py`
- `python scripts/validate_production.py` with production environment values
- `npm run build` inside `frontend/` for type checking and the production Vite bundle
- `npm audit --audit-level=high` inside `frontend/`

## CI

- Ruff passes.
- Mypy passes.
- Dependency audit passes or exceptions are documented.
- PostgreSQL pytest job passes.
- PostgreSQL Alembic migration smoke passes.
- `scripts/verify_postgres_rls.py` passes with a non-owner app role.
- Docker image builds.

## Staging

- API and worker are deployed as separate processes.
- API/worker use a non-owner app database role.
- Alembic ran with the migration/table-owner role.
- `GET /health` is green.
- Authenticated `GET /v1/health/deep` reports DB, Redis, worker, jobs, vector, and configured LLM provider.
- `/app` serves the React build from `frontend/dist`.
- `/v1/client-config` exposes production legal URLs and no secrets.
- `python scripts/smoke_api.py` passes.
- `k6 run load/k6-health.js` passes.
- `k6 run load/k6-api-flow.js` passes.
- Backup and restore drill completed.
- `reports/closed-beta-evidence-*.json` and `reports/closed-beta-gap-report-*.md` were generated from the target environment with no failed steps and only understood infrastructure blockers.

## Tag

Tag only after CI and staging are green:

```bash
git tag v1.0.0-backend
git push origin v1.0.0-backend
```
