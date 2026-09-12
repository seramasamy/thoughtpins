# Backend Deployment Templates

These templates package the backend, public website and web app. They assume
managed PostgreSQL and Redis, shared authenticated Qdrant, and two runtime
processes:

- API: `python -m thoughtpins.server --api-only`
- Worker: `python -m thoughtpins.worker`

Public domain routing is documented in `deploy/DOMAIN_AND_DNS.md`. The default
production shape is:

- `thoughtpins.com`: static public/legal site from `site/`.
- `www.thoughtpins.com`: redirect to `thoughtpins.com`.
- `thoughtpins.com`: backend-served web app at `/app`.
- `api.thoughtpins.com`: backend `/v1` API.
- `staging.thoughtpins.com` and `api-staging.thoughtpins.com`: staging.

The machine-readable closed-beta handoff is `deploy/closed-beta-deployment-packet.json`; run `python scripts/check_deployment_packet.py` after editing deploy, DNS, store, env, or runbook files. The generated launch handoff is `reports/closed-beta-launch-packet-*.md`; create it with `python scripts/generate_launch_packet.py` after evidence collection and validate the generator with `python scripts/check_launch_packet.py`.

Required production checks after deploy:

```bash
python scripts/release_check.py
python scripts/check_deployment_packet.py
python scripts/check_launch_packet.py
python scripts/check_host_capabilities.py
python scripts/generate_launch_packet.py
python scripts/check_domain_readiness.py
python scripts/validate_production.py
alembic upgrade head
DATABASE_URL=<migration-role-url> RLS_VERIFY_DATABASE_URL=<app-role-url> python scripts/verify_postgres_rls.py
python scripts/smoke_api.py
k6 run load/k6-health.js
k6 run load/k6-api-flow.js
```

For a local closed-beta rehearsal with Docker Desktop running, use:

```powershell
.\scripts\run_compose_rehearsal.ps1
```

Linux/macOS/CI equivalent:

```bash
python scripts/run_compose_rehearsal.py
```

That Compose path uses a one-shot `migrate` service with the schema-owner role,
then starts API and worker with the non-owner `thoughtpins_app` role so RLS is
verified under the same runtime assumption expected in staging.

For staging, the same sequence is wrapped by:

```powershell
.\scripts\run_staging_smoke.ps1
```

Override hostnames if needed:

```powershell
.\scripts\run_staging_smoke.ps1 `
  -ApiBaseUrl https://api-staging.thoughtpins.com `
  -PublicUrl https://thoughtpins.com `
  -AppUrl https://staging.thoughtpins.com
```

Use a migration/table-owner database role only for Alembic. The API and worker
must use the non-owner app role so PostgreSQL RLS is meaningful.

The Docker image builds the React client into `frontend/dist`, keeps
`frontend/static` as a fallback, and copies `site/` into the runtime image. The
backend-served web app is available at `/app`, and `/privacy`, `/terms`,
`/support`, `/account/delete`, `/ai-disclosure`, `/robots.txt`, `/sitemap.xml`,
and `/assets/*` serve the reviewed static public-site files when present. Native
mobile clients should still use the documented `/v1` API contract instead of
depending on the web client implementation.

For a single-VM HTTPS reverse proxy, adapt
`deploy/Caddyfile.thoughtpins.example`. For managed platforms, configure the
same hostnames and TLS certificates in the provider dashboard.




The Compose rehearsal uses the isolated project name `thoughtpins-rehearsal` by default and writes `reports/compose-rehearsal-*.json` for handoff evidence. Use `scripts/run_compose_rehearsal.py` when PowerShell is unavailable. Override with `-ProjectName` and `-ReportPath` when needed; custom Compose project names must start with `thoughtpins-` so teardown remains isolated to Thought Pins rehearsal services.
When Docker or Playwright cannot run on the current workstation, produce portable proof on a capable host and validate it before regenerating evidence:

```bash
python scripts/check_external_proof_artifacts.py \
  --compose-report reports/compose-rehearsal-<stamp>.json \
  --playwright-report reports/playwright-web-smoke.json \
  --web-smoke-dir reports/web-smoke

python scripts/collect_closed_beta_evidence.py \
  --api-base-url https://api-staging.thoughtpins.com \
  --telegram-api --web-smoke --strict-complete \
  --compose-rehearsal-report reports/compose-rehearsal-<stamp>.json \
  --playwright-report reports/playwright-web-smoke.json \
  --web-smoke-dir reports/web-smoke
```

The verifier rejects stale, failed, partial, or secret-like artifacts and requires the desktop/tablet/mobile review screenshots. The Playwright suite also exercises login, maintenance/offline states, article-link ingestion, file upload, memory-card provenance/vault paths, export, and in-app account deletion. That lets local packets distinguish true code gaps from host limitations without pretending the current machine ran Docker or a browser.

For final closed-beta evidence, keep `--strict-complete` on the collector command. A non-strict run may still be useful for diagnostics, but it is not sufficient for a release handoff when any proof is skipped or blocked.

Store-review traceability is generated separately as `reports/store-readiness-matrix-*.md`. It maps each Apple/Google requirement in `deploy/store/store-policy-requirements.json` to current evidence, native handoff flows, public URLs, and remaining console/account tasks.
