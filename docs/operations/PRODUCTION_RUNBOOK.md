# Thought Pins Production Runbook

## Deploy

1. Run the offline release gate:
   - `python scripts/release_check.py`
   - `python scripts/smoke_startup_shutdown.py`
   - `python scripts/release_check.py --strict-quality` on a machine that can
     install `ruff`, `mypy`, and `pip-audit`
2. Build the image from this directory.
3. Provide production environment variables from `.env.production.example`.
   Generate `DATA_ENCRYPTION_KEY` with:
   `python -c "from thoughtpins.crypto import generate_key; print(generate_key())"`
   Keep `VOICE_ARCHIVE_ENABLED=false` for public store deployments. Configure a
   complete external `TRANSCRIPTION_*` endpoint, or install the `voice` extra
   when deliberately operating local transcription on the API host.
4. Run `python scripts/validate_production.py`.
5. Run `alembic upgrade head`.
6. Start the authenticated Qdrant service, then API and worker:
   - Qdrant must be reachable at `QDRANT_URL`; keep it private to the service
     network and set the same `QDRANT_API_KEY` on Qdrant, API, and worker.
   - API: `python -m thoughtpins.server --api-only`
   - Worker: `python -m thoughtpins.worker`
7. Check:
   - `GET /health`
   - authenticated `GET /v1/health/deep`
   - authenticated `GET /v1/metrics`
   - `GET /app`
   - `GET /v1/client-config`
8. Verify tenant isolation:
   - `python scripts/check_rls_static.py`
   - `DATABASE_URL=<migration-role-url> RLS_VERIFY_DATABASE_URL=<app-role-url> python scripts/verify_postgres_rls.py`
9. Confirm production uses `RUN_STARTUP_RECOVERY=false`; durable ingestion jobs
   are recovered by the worker's tenant-aware relay. Keep
   `WORKER_RECOVERY_INTERVAL_SECONDS` between 10 and 3600 seconds. A healthy
   queue normally leaves no old `pending`, `retry`, or `queued` rows; the relay
   republishes stale handoffs and conditionally claims duplicate deliveries.
10. Run app-flow smoke/load checks:
   - `python scripts/smoke_api.py`
   - `python scripts/run_local_load_smoke.py` for an isolated workstation proof
   - `python scripts/run_local_cross_browser_audit.py` for Chromium, Firefox,
     and WebKit screenshots against a disposable local API
   - `k6 run load/k6-health.js`
   - `k6 run load/k6-api-flow.js`

## Local Bootstrap

Use this on a fresh development/staging workstation:

```powershell
.\scripts\bootstrap_local.ps1
```

If local voice transcription is needed on the workstation, run:

```powershell
.\scripts\bootstrap_local.ps1 -WithVoice
```

If the private Telegram adapter and its OCR dependencies are also needed, run:

```powershell
.\scripts\bootstrap_local.ps1 -WithTelegramHeavy
```

Before packaging, publishing, or copying the repo to a review machine, remove
local smoke-test debris without touching source or secrets:

```powershell
python scripts\clean_local_artifacts.py --json
python scripts\clean_local_artifacts.py --apply
```

The cleanup command preserves root `data/`, `vault/`, `logs/`, `backups/`,
`reports/`, and `frontend/dist` by default. Use `--include-runtime-state` only
when intentionally wiping local SQLite, vault, logs, and backup state. Use
`--include-reports` or `--include-build` only when preparing a source-only
public package. ACL-locked Windows pytest folders may require an elevated shell.

## Closed-Beta Evidence

Collect a host capability packet and redacted local evidence packet before any closed-beta handoff. The machine-readable deployment handoff lives at `deploy/closed-beta-deployment-packet.json` and is validated by `python scripts/check_deployment_packet.py`. Prefer `collect_local_closed_beta_evidence.py` when no staging API is already running; it starts a disposable API, keeps SQLite/vault/vector/backup stores in `.tmp/local-evidence`, runs the collector, and shuts down only its own child process:

```powershell
python scripts/check_host_capabilities.py
python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke
python scripts/collect_closed_beta_evidence.py
python scripts/collect_closed_beta_evidence.py --web-smoke
python scripts/collect_closed_beta_evidence.py --api-base-url http://127.0.0.1:8420 --telegram-api
```

The host preflight writes `reports/host-capabilities-*.json`. The collector writes `reports/closed-beta-evidence-*.json`, records pass/fail/skipped/blocked
status for release, compliance, review account, public export, backup restore,
Obsidian vault stress, production parity, Docker availability, runtime smoke,
Telegram smoke, article provider smoke, and Playwright web smoke. It also writes `reports/store-readiness-matrix-*.md`, which maps Apple/Google store requirements to current evidence, `reports/closed-beta-gap-report-*.md`, which separates code gaps from infrastructure/account-only blockers, and `reports/closed-beta-launch-packet-*.md`, which converts the same evidence into local-founder, web-beta, native-store, Obsidian, and infrastructure go/no-go tracks. It also writes `reports/closed-beta-objective-audit-*.md`, which maps the six closed-beta objective areas to the exact evidence steps that prove or block them. Output tails
are redacted before being stored. A blocked Docker daemon or browser spawn is an
environment gap, not a code pass for final release; rerun the same command on a
Docker/Linux or CI host before tagging. When a capable host has already produced Compose and Playwright proof artifacts, copy `reports/compose-rehearsal-*.json`, `reports/playwright-web-smoke.json`, and `reports/web-smoke/*.png` back into this repo and validate them with:

```powershell
python scripts/check_external_proof_artifacts.py `
  --compose-report reports\compose-rehearsal-<stamp>.json `
  --playwright-report reports\playwright-web-smoke.json `
  --web-smoke-dir reports\web-smoke

python scripts/collect_closed_beta_evidence.py `
  --api-base-url https://api-staging.thoughtpins.com `
  --telegram-api --web-smoke --strict-complete `
  --compose-rehearsal-report reports\compose-rehearsal-<stamp>.json `
  --playwright-report reports\playwright-web-smoke.json `
  --web-smoke-dir reports\web-smoke
```

Valid external proof can supersede this workstation's Docker/browser limitations in the generated gap and launch packets; failed, stale, partial, or secret-like artifacts are rejected. The required `reports/web-smoke/web-proof-manifest.json` plus `reports/web-smoke/*.png` set covers desktop/tablet/mobile shells, auth, library ingestion, memory-card provenance, account export/delete, maintenance, and offline states.

Use `--strict-complete` for the final closed-beta handoff or tag gate. It keeps exploratory evidence runs useful on restricted workstations, but exits nonzero until Docker/RLS, Playwright screenshots, runtime, Telegram, article, backup, vault, and store-readiness proof are all present with no skipped or blocked checks.

## One-Command Host Proof

On an elevated Windows shell, CI runner, or Linux/macOS host where Docker and
Playwright browser spawning are available, run the full closed-beta proof path:

```powershell
python scripts\run_closed_beta_host_proof.py --full-tests
```

This runs generated-artifact cleanup, host capability preflight, Docker Compose
rehearsal, PostgreSQL RLS verification, backup/restore, Playwright browser
smoke screenshots for the shell and review-critical flows, external proof validation, Telegram/article smoke, and strict closed-beta evidence collection. It writes deterministic proof artifacts to
`reports/compose-rehearsal-latest.json`, `reports/playwright-web-smoke.json`,
and `reports/web-smoke/`. Compose teardown is delegated to the scoped
`thoughtpins-*` rehearsal project so unrelated Docker projects are not touched.

## Local Production Rehearsal

Use this when Docker Desktop is running and you want a closed-beta rehearsal on
one machine:

```powershell
.\scripts\run_compose_rehearsal.ps1
# optional deterministic proof path:
.\scripts\run_compose_rehearsal.ps1 -ProjectName thoughtpins-rehearsal -ReportPath reports\compose-rehearsal-latest.json
```

On Linux, macOS, or CI runners without PowerShell, use the equivalent Python runner:

```bash
python scripts/run_compose_rehearsal.py
python scripts/run_compose_rehearsal.py --project-name thoughtpins-rehearsal --report-path reports/compose-rehearsal-latest.json
```

When Docker Engine is available inside WSL but Docker Desktop is not, the same
runner can invoke Docker entirely inside one named distribution:

```powershell
python scripts\run_compose_rehearsal.py --wsl-distro Ubuntu-22.04 --project-name thoughtpins-rehearsal-wsl
```

The rehearsal starts only this Compose project, runs PostgreSQL 16, Redis 7,
an authenticated shared Qdrant service,
the one-shot Alembic migration service, the API, and the worker, then verifies:

- API and worker use the non-owner `thoughtpins_app` database role.
- Alembic runs through the schema-owner role and grants runtime privileges to
  the app role via `THOUGHTPINS_APP_DB_ROLE`.
- PostgreSQL RLS is checked through `RLS_VERIFY_DATABASE_URL`.
- Deep health, HTTP smoke, async job completion, and backup restore pass.
- Qdrant remote-mode connectivity, vault exports, and reports are persisted in
  named Compose volumes. API and worker never open the same local Qdrant file.

The runner treats the external inference smoke as part of the release result.
A healthy database, queue, and vector store do not turn an upstream quota,
authentication, or model failure into a passing end-to-end rehearsal.

Use `/health` only for process liveness. Load balancers and orchestrators should
use the public `/ready` endpoint; it returns only dependency names and generic
statuses, fails with HTTP 503, and bounds dependency evaluation to five seconds.
Authenticated operator diagnostics remain at `/v1/health/deep`.

Run the destructive portion of vector recovery only through the isolated drill.
It creates and removes a random `thoughtpins_recovery_drill_*` collection and
refuses any other fixture namespace:

```bash
QDRANT_URL=http://127.0.0.1:6333 QDRANT_API_KEY=<rehearsal-key> \
  python scripts/verify_qdrant_snapshot_restore.py
```

Prove a real PostgreSQL custom-format dump and isolated restore without ever
targeting the active database for deletion:

```powershell
$env:DATABASE_URL = "<owner-postgres-url>"
python scripts\verify_postgres_dump_restore.py `
  --compose-project thoughtpins-rehearsal-wsl `
  --wsl-distro Ubuntu-22.04 `
  --report-path reports\postgres-restore-current.json
```

The verifier accepts only a `thoughtpins-*` Compose project, creates a random
`thoughtpins_restore_drill_*` database, compares every public-table row count,
Alembic revision, RLS flag, and policy, and removes the fixture, dump, and
scratch database before writing a passing report.

After installing the pinned local k6 binary, exercise independently
authenticated tenants and prove both positive ownership and negative
cross-tenant access:

```powershell
$env:DATABASE_URL = "<owner-postgres-url>"
python scripts\run_compose_load_rehearsal.py `
  --users 10 --iterations-per-user 1 --duration 20s `
  --report-path reports\load\compose-multi-tenant-current.json
```

This test seeds disposable isolation probes, queues real asynchronous work,
waits for the worker backlog to drain, rejects failed/dead-letter jobs, runs
normal account lifecycle cleanup, and verifies that no tenant-owned fixture
rows remain.

By default both rehearsal scripts use the isolated Compose project name `thoughtpins-rehearsal`, tear down only that project at the end, and write `reports/compose-rehearsal-*.json`. Use `-ProjectName <name>` when you need a different project namespace; custom names must start with `thoughtpins-` so teardown cannot target unrelated Compose projects. Use `-ReportPath <path>` for a deterministic proof artifact, and `-KeepRunning` when you want to inspect the running API/web app after verification. On an existing Postgres volume created before the app role init
script existed, recreate the volume or manually create the `thoughtpins_app`
role before rerunning the rehearsal.

## Rollback

1. Stop new deploy traffic at the load balancer.
2. Start the previous known-good image.
3. If the migration changed schema incompatibly, run the matching Alembic downgrade only after confirming the previous image requires it.
4. Verify `/health`, `/ready`, `/v1/health/deep`, login, entry queueing, and worker heartbeat.

## Backup

Back up these stores together:

- PostgreSQL database.
- Vault path.
- Qdrant service snapshots or managed-service backups.
- Voice archive path when a private/self-hosted deployment has explicitly
  enabled retained audio. Treat this as sensitive encrypted user data and keep
  it in the same retention, restore, and erasure boundary as PostgreSQL.
- Object/file storage if introduced later.

Minimum schedule:

- PostgreSQL: continuous WAL archiving or daily snapshot plus point-in-time recovery.
- Vault/Qdrant data: daily snapshot.
- Restore drill: monthly.

Set `BACKUPS_PATH` alongside `VAULT_PATH` and `REPORTS_PATH` when backup storage should live outside the project root. Local-development Qdrant lock files are excluded from local zip backups. Production Qdrant must use its native snapshot or managed backup path; vectors remain rebuildable from the relational source of truth.

Every Thought Pins local ZIP backup is accompanied by `<archive>.sha256` and
`<archive>.private-backup.json` in the same directory. The JSON sidecar records
the archive name, size, SHA-256, secret-bearing status, encryption scheme, and
an optional recovery-key reference. Restore verifies the adjacent provenance
before extraction. Do not copy a password into the sidecar unless the archive
is an explicitly private local artifact and that weak recovery tradeoff is
intentional; production encryption keys belong in a password manager, KMS, or
platform secret store and the sidecar should contain only its reference.

For a private development snapshot of source, relevant documentation, and the
current `.env`, use the encrypted source-backup path:

```powershell
$recoveryKeyProtectionPassword = Read-Host `
  "Recovery-key protection password" -AsSecureString
$backup = .\scripts\create_private_source_backup.ps1 `
  -RecoveryKeyProtectionPassword $recoveryKeyProtectionPassword
.\scripts\verify_private_source_backup.ps1 `
  -SidecarPath $backup.PrivateRecoverySidecar `
  -RecoveryKeyProtectionPassword $recoveryKeyProtectionPassword
$recoveryKeyProtectionPassword = $null
```

This produces an AES-256 7z archive with encrypted headers, SHA-256 and metadata
sidecars, and a second AES-256 archive containing the randomly generated
recovery key. Both archives encrypt their headers. The operator-managed password
that protects the recovery-key archive is not written to metadata or disk by the
backup utility; retain it in a password manager. Never publish any of these
private artifacts.

## Restore

1. Verify every local archive against its adjacent SHA-256 and recovery
   sidecar before opening or transferring it.
2. Restore PostgreSQL into a staging database.
3. Restore the vault and Qdrant snapshot to staging storage.
4. Run `alembic current` and `alembic upgrade head` if needed.
5. Verify the restored Alembic revision, representative tenant/account counts,
   queue state, vault file hashes, and Qdrant point payload provenance.
6. Run RLS, deep-health, authenticated API-flow, and account export tests
   against the restored environment.
7. Promote only after tenant isolation and deletion checks pass. Never restore
   a drill database over the active production database.

## TLS

Terminate TLS at the reverse proxy or managed load balancer. Forward:

- `X-Forwarded-For`
- `X-Forwarded-Proto`
- `X-Request-ID`

Only expose the API over HTTPS outside local development.

## Graceful Shutdown

API instances should receive SIGTERM and stop accepting new traffic before process exit. Uvicorn handles request draining when the orchestrator gives a sufficient termination grace period. Use at least 30 seconds.

Workers should stop after current tasks finish. Celery workers should receive TERM, not KILL, and should run with `task_acks_late=true` so interrupted tasks return to the queue.

## Launch Gate

Do not open public signup until:

- RLS is verified with the exact production app database role.
- API service runs as the non-owner app DB role; migrations run as the owner
  role only during deploy.
- `python -m pytest` passes locally and in CI.
- PostgreSQL CI test job passes.
- `python scripts/forbidden_scan.py` passes.
- `pip-audit .` passes for the deployable project dependency graph.
- k6 health test passes: `k6 run load/k6-health.js`.
- k6 API flow passes: `k6 run load/k6-api-flow.js`.
- Backup restore has been tested on staging.
- `/app` serves the React build and the Legal screen has live production URLs.
- Public privacy policy, terms, support, account deletion, and AI disclosure
  URLs are configured.
- LLM provider credentials are configured with explicit timeout/retry settings.
- `DATA_ENCRYPTION_KEY` is a valid Fernet key and permanent per-user API keys
  are disabled with `ALLOW_USER_API_KEYS=false`.
- Public store services have `VOICE_ARCHIVE_ENABLED=false`; the deep health
  response reports a ready transcription path and a disabled archive.
- `VECTOR_MODE=qdrant_remote`, Qdrant authentication is enabled, and deep
  health confirms the shared vector service from both API and worker networks.

Use separate PostgreSQL roles in production: a migration role that owns schema
objects and a non-owner app role that receives table privileges. Running the API
as the owner role weakens RLS because PostgreSQL owners can bypass policies.

Deployment templates live in `deploy/`; adapt the app name, region, and managed
PostgreSQL/Redis bindings for the chosen provider.
