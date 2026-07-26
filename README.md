# Thought Pins

AI journal companion backend for iOS, Android, and Web.

Status: release-candidate backend and web app foundation. The repository now has a runnable
`thoughtpins` package, versioned API routes, JWT refresh sessions, API-key
bootstrap auth, user-scoped journal data models, async ingestion jobs, account
export/delete, Alembic migrations, Docker Compose for PostgreSQL/Redis, and
safer environment configuration. Public launch still requires infrastructure
proofs: PostgreSQL RLS verification on the chosen host, staging smoke and load
tests, public legal URLs, signed native builds, and rotated production secrets.

## What It Does

Thought Pins stores journal entries, extracts structured memories with an LLM,
builds people/place/event context, supports question answering over the journal,
and can export reports, graphs, and Obsidian-compatible notes.

Core runtime surfaces:

- FastAPI backend with `/v1` routes.
- Backend-served React web client at `/app`, with a static fallback.
- SQLAlchemy relational schema with tenant ownership columns and Alembic
  migrations.
- Password login with short-lived JWT access tokens and rotating refresh
  sessions.
- Optional OAuth ID-token login for Google and Apple when client IDs are
  configured.
- Async entry processing with Celery worker support, local thread fallback, job
  status tracking, retries, and dead-letter state.
- Job listing, retry, and cancellation APIs for app-grade processing UX.
- User-initiated voice notes with visible recording state, provider-neutral
  transcription, and temporary-audio cleanup. Public builds discard recordings
  after transcription; private/self-hosted deployments can separately enable a
  consented, encrypted, tenant-scoped personal archive.
- Request IDs, structured error envelopes, Prometheus-style metrics, and deep
  health checks for DB, Redis, worker heartbeat, job backlog, vector storage,
  and configured LLM provider.
- Security headers, request body limits, endpoint-specific rate limits, and
  compact audit logs for auth/data lifecycle events.
- Optional local/private chat adapters can be run outside the store product through the public `/v1` API.
- Provider-neutral OpenAI-compatible AI runtime supplied through generic
  `LLM_*` settings.
- Tenant-filtered Qdrant retrieval: local storage for founder development and
  an authenticated shared service for staging/production API and workers.
- Local-first reading/document memory for URLs, pasted articles, PDFs/text
  uploads, with provenance fields, source/title/topic/concept extraction,
  chunk retrieval, and metadata-only handling when a page does not expose
  readable text.
- Typed memory ontology inspired by temporal graph-memory systems: extraction is
  constrained to a small set of entity and relationship types with source/target
  guardrails, while SQL remains the source of truth.
- Hybrid retrieval across exact text, BM25-style lexical scoring with rare-clue,
  phrase, and proximity signals, vector search, document/source titles, and SQL
  graph-neighborhood evidence.
- Query-conditioned social-episodic ranking preserves speakers, claim status,
  causes, outcomes, places, open loops, and corrections. Explicit 1-5 star
  ratings remain bounded preference signals and cannot override a materially
  better query match.
- A provenance-aware evidence plan sits between retrieval and answer synthesis,
  keeping hearsay, inference, disputed claims, and retractions labeled rather
  than silently turning them into facts.
- Untrusted-memory prompt boundaries: retrieved journals, chat, OCR, and source
  text remain user/source evidence rather than system instructions, with
  instruction-shaped content labeled before model injection.
- Optional graph backend adapter with `internal_sql` as the source-of-truth
  default and Graphiti available as an auxiliary/shadow backend when the
  `graph` extra and graph infrastructure are configured.
- Obsidian, report, and graph exports scoped by authenticated user where called
  from the API.

The current architecture and its honest gaps are graded in
`docs/architecture/MEMORY_ARCHITECTURE_REVIEW.md`. Dataset governance,
calibration, independent holdout metrics, and benchmark limits are documented
in `docs/architecture/EXTERNAL_MEMORY_BENCHMARKS.md`.

## Quick Start

For maintainers and AI coding agents, read `ARCHITECTURE_MODULES.md` before
adding features. It lists the owning module for each gear so new work does not
accumulate in the adapter files.

```powershell
cd path\to\thoughtpins
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
copy .env.example .env
.\scripts\run_local.ps1 -ApiOnly
```

Local transcription is an optional dependency because the model runtime is too
large for the base API image:

```powershell
pip install -e ".[dev,voice]"
```

Alternatively, configure an OpenAI-compatible transcription endpoint with the
generic `TRANSCRIPTION_*` settings. `TRANSCRIPTION_PROVIDER=local` requires the
`voice` extra; production validation fails fast when neither a usable local
runtime nor a complete external configuration is present.

Release and CI installs are reproducible through `uv.lock`; the container uses
the hash-locked `requirements-prod.lock`. Run
`python scripts/check_dependency_locks.py` after any dependency change.

Default local mode uses SQLite and does not require API auth unless
`REQUIRE_API_AUTH=true`.

Open the core web client after the API starts:

```text
http://127.0.0.1:8420/app
```

When `REQUIRE_API_AUTH=false`, the web client can continue in local mode and
uses the same default-user path as the API. When auth is required, it uses JWT
login and rotating refresh sessions.

The functional web client is chat-first: email or phone registration/login,
conversation replay, memory cards, explicit capture, entries, jobs,
article/document library ingestion, account export/delete, preferences, device
registration, legal acceptance, legal/support links, and responsive desktop,
tablet, and mobile layouts. The backend serves `frontend/dist` only when
`npm run build` writes `.thoughtpins-build.json`; otherwise it falls back to the
checked-in `frontend/static` recovery app. `npm run build` performs the
TypeScript check and emits the production Vite bundle used by the backend.

Prepare the deterministic fictional reviewer profile after migrations:

```powershell
python scripts/seed_local_demo_corpus.py --json
```

The seed is idempotent and contains seven dated journal entries, three reading
sources, connected people/places/concepts, one encrypted private reflection,
and explicit 1-5 importance ratings. It is local test data and is excluded from
the public source export.

For any shared environment, set:

```env
ENVIRONMENT=production
REQUIRE_API_AUTH=true
API_KEY=<long-random-bootstrap-key>
ALLOW_USER_API_KEYS=false
RETURN_API_KEY_ON_REGISTER=false
JWT_SECRET=<long-random-jwt-secret>
AUTO_CREATE_TABLES=false
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/thoughtpins
REDIS_URL=redis://host:6379/0
RATE_LIMIT_ENABLED=true
PROCESS_ENTRIES_ASYNC=true
INGESTION_QUEUE_BACKEND=celery
CELERY_BROKER_URL=redis://host:6379/1
CELERY_RESULT_BACKEND=redis://host:6379/2
LLM_PROVIDER=openai_compatible
LLM_API_KEY=<provider-key>
LLM_BASE_URL=<openai-compatible-base-url>
LLM_MODEL=<chat-model>
LLM_FALLBACK_MODEL=<fallback-model>
LLM_EXTRACTION_MODEL=<fast-structured-extraction-model>
LLM_THINKING=disabled
TRANSCRIPTION_PROVIDER=hosted
TRANSCRIPTION_API_KEY=<transcription-key>
TRANSCRIPTION_BASE_URL=<openai-compatible-transcription-base-url>
TRANSCRIPTION_MODEL=<transcription-model>
VOICE_ARCHIVE_ENABLED=false
DATA_ENCRYPTION_KEY=<fernet-key>
PRIVACY_POLICY_URL=https://thoughtpins.com/privacy
TERMS_URL=https://thoughtpins.com/terms
SUPPORT_URL=https://thoughtpins.com/support
ACCOUNT_DELETION_URL=https://thoughtpins.com/account/delete
AI_DISCLOSURE_URL=https://thoughtpins.com/ai-disclosure
RUN_STARTUP_RECOVERY=false
```

Apply schema migrations before starting a shared deployment:

```powershell
alembic upgrade head
```

Local PostgreSQL/Redis smoke environment:

```powershell
docker compose up --build
```

Run a standalone Celery worker when the queue backend is enabled:

```powershell
$env:PYTHONPATH="src"
python -m thoughtpins.worker
```

Validate a production environment before deploy:

```powershell
$env:PYTHONPATH="src"
python scripts/validate_production.py
```

Export/check the API contract:

```powershell
$env:PYTHONPATH="src"
python scripts/export_openapi.py --check
```

Run a deployed API smoke test:

```powershell
$env:PYTHONPATH="src"
python scripts/smoke_api.py
```

Run a locked local runtime smoke test without public signup:

```powershell
$env:PYTHONPATH="src"
python scripts/smoke_founder_local.py
```

Validate a configured private chat-adapter token without printing secrets:

```powershell
python scripts/smoke_telegram_api.py
```

Run the full offline release gate before handing the backend to mobile work:

```powershell
$env:PYTHONPATH="src"
python scripts/release_check.py
python scripts/smoke_startup_shutdown.py
python scripts/run_local_load_smoke.py
python scripts/run_local_cross_browser_audit.py
python scripts/check_store_submission_packet.py
python scripts/check_web_app_contract.py
python scripts/check_launch_packet.py
python scripts/check_host_capabilities.py
python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke
python scripts/collect_closed_beta_evidence.py --web-smoke
```

The local load smoke downloads nothing and starts only its own disposable API.
It runs the same k6 health and authenticated app-flow scripts used in staging,
then verifies graceful shutdown, port release, and temporary-data removal. Pass
`--k6 <path>` when k6 is not on `PATH`. Local SQLite results are regression
evidence, not a substitute for capacity testing against the deployed
PostgreSQL/Redis topology.


On an elevated Windows shell or any host where Docker and Playwright can spawn
browsers, run the full closed-beta proof bundle:

```powershell
python scripts\run_closed_beta_host_proof.py --full-tests
```

This creates the Compose rehearsal report, Playwright JSON report, review
screenshots, and strict closed-beta evidence packet in one pass. The web proof requires `reports/web-smoke/web-proof-manifest.json`, desktop/tablet/mobile shell screenshots, and auth, library ingestion, memory-card provenance, account export/delete, maintenance, and offline state screenshots.
Run `python scripts/check_host_capabilities.py --with-browser-smoke` first when Docker, Playwright, Swift, Android, or Java proof is unclear; it writes `reports/host-capabilities-*.json` without treating host limitations as code failures. Use `collect_local_closed_beta_evidence.py` for a one-command local rehearsal: it starts a disposable API on a random local port, points SQLite/vault/vector/backup paths at `.tmp`, runs the redacted evidence collector, then shuts down only its own child process. The evidence collector writes a redacted `closed-beta-evidence-*.json`, a `closed-beta-gap-report-*.md` handoff separating code gaps from infrastructure/browser/provider/store-account work, and a `closed-beta-launch-packet-*.md` go/no-go packet for private local adapters, web beta, native shells, Obsidian export, and Docker/RLS proof, plus a `closed-beta-objective-audit-*.md` requirement-by-requirement audit of the six closed-beta goals.

Rebuild and verify the memory vector index:

```powershell
python scripts/reindex_vectors.py --verify-query "memory router"
python scripts\memory_maintenance.py --reindex
python scripts\evaluate_memory_quality.py
python scripts\evaluate_memory_infra.py
python scripts\evaluate_social_relevance.py --cases 5000
python scripts\evaluate_public_domain_social_corpus.py --sources 300
```

Use a hosted embedding provider for production-quality memory search:

```env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

After changing the embedding provider or model, rebuild the derived vector
index with `python scripts/reindex_vectors.py --verify-query "memory router"`.
This does not change the chat model; the LLM provider and embedding provider
are intentionally separate.

Structured journal extraction is intentionally bounded for Telegram
responsiveness. Provider-specific thinking/reasoning can remain enabled for
conversational answers when the provider supports it, but extraction calls run
without thinking and use `LLM_EXTRACTION_MODEL` plus
`LLM_EXTRACTION_MAX_TOKENS` to avoid slow, oversized JSON from the long-context
chat model. Structured calls request standard JSON-object mode, automatically
fall back when a compatible endpoint does not implement it, and use a tested
syntax-repair boundary before Pydantic validation.

Article URL ingestion is rights-aware by design. It fetches public page text with a
normal local request, never impersonates crawlers, strips authentication state,
defeats publisher controls, or substitutes unauthorized archives. If readable text
is unavailable, Thought Pins saves source metadata and looks for an authorized open copy.
Optional providers can be enabled for public pages. The recommended local chain
is `local,jina,firecrawl`: the app tries a normal fetch first, then Jina Reader
for cheap clean markdown, then Firecrawl for JavaScript-heavy public pages.
Apify is still available as an opt-in specialist fallback when a chosen Actor is
configured.

Substack links receive a first-party path before that generic chain. Thought
Pins checks the publication's official RSS feed, matches both publication URLs
and `open.substack.com` share links to the post slug, and stores the canonical
publisher URL. Only text exposed by the public feed is ingested. A paid-only or
otherwise gated post remains a source record and original link until the user
adds text they are authorized to access.

Scholarly DOI links also use an open-access resolution step. When an authorized
repository or openly licensed copy exists, Thought Pins reads that copy and keeps
the original publisher link as provenance. Otherwise the source remains metadata-only.

Every saved link becomes a document source with source domain, publisher label
where inferable (for example WSJ, The Economist, Bloomberg), article title,
author/date when exposed, raw text, chunks, a short summary, detected topics,
and key concepts. Thought Pins indexes both the full source chunks and a compact
source-characteristics memory so later chat can recall not only what happened
in your journal, but also what you have read.

Stored source text remains private retrieval material. Portable exports include
full source bodies only for user-authored, user-owned, public-domain, or openly
licensed material; other sources export metadata, provenance, and derived memory.
Ordinary source cards
show reader-facing metadata such as publication, author, date, topics, key
ideas, and processing status; they do not expose full source text, reader
provider names, access-policy diagnostics, internal IDs, or retrieval scores.
The visible source action always prefers the canonical publisher URL.

```env
ARTICLE_FETCH_PROVIDERS=local,jina,firecrawl
OPEN_ACCESS_RESOLUTION_ENABLED=true
OPEN_ACCESS_CONTACT_EMAIL=support@thoughtpins.com
JINA_API_KEY=
FIRECRAWL_API_KEY=
# ARTICLE_FETCH_PROVIDERS=local,jina,firecrawl,apify
APIFY_API_TOKEN=
APIFY_READER_ACTOR=
LIBRARY_EXTRACT_GRAPH=false
```

To smoke-test configured readers without saving anything, run
`python scripts/smoke_article_fetch_providers.py`.

To test the full public-link ingestion path with cleanup, run
`python scripts/smoke_live_article_ingest.py`. This uses a disposable user and
an isolated Qdrant path by default, then deletes the generated source, chunks,
memories, and vector points.

For a combined local engineering pass with live article and private adapter checks:

```powershell
python scripts/run_engineering_checks.py --skip-release --api-base-url http://127.0.0.1:8420 --live-article --telegram-api
```

Known subscription publishers are treated as metadata-only by default through
`ARTICLE_RESTRICTED_DOMAINS`. If a saved link is from one of those domains, or
if the fetched text contains restricted-access markers, Thought Pins saves the
source metadata without retaining the unavailable source body.

Graph infrastructure is local-first. The default is `GRAPH_PROVIDER=internal_sql`.
To experiment with Graphiti without making it a production dependency, install
`pip install -e .[graph]`, set `GRAPH_SHADOW_ENABLED=true`, and keep
`GRAPH_PROVIDER=internal_sql` until `scripts/evaluate_memory_infra.py` proves
the external graph improves recall. Promote Graphiti only after tenant deletion,
export, and recall-quality tests pass for the chosen backend.
`scripts/validate_production.py` rejects external graph and shadow modes until
that deletion contract is implemented and verified, so an experiment cannot
silently become a production data-retention dependency.

Clear local journal/library content before a fresh test cycle:

```powershell
python scripts\clear_memory_data.py --dry-run
python scripts\clear_memory_data.py --yes
```

This creates a pre-clear backup by default, preserves users/auth, clears
journal/library/graph/report rows, clears vault/report/cache files, and resets
the derived vector index.

Clean generated local smoke-test artifacts before packaging or handing off the
repo. Dry-run is the default and root runtime state is preserved unless you ask
for it explicitly:

```powershell
python scripts\clean_local_artifacts.py --json
python scripts\clean_local_artifacts.py --apply
# only when intentionally wiping local runtime state too:
python scripts\clean_local_artifacts.py --apply --include-runtime-state
```

On restricted Windows shells, old pytest temp directories may remain ACL-locked
until the workspace is reopened as Administrator.

Bootstrap a fresh workstation:

```powershell
.\scripts\bootstrap_local.ps1
```

## Private Local Adapter

The personal chat adapter is now split into a sibling private project:
`../thoughtpins-founder-telegram-adapter`. It uses the same `/v1/chat`, export,
health, auth, memory, and document-ingestion paths as the web/mobile API through
normal HTTP credentials.

Store builds do not ship that adapter, local secrets, or owner-only controls.
Production startup validation still blocks local adapter flags outside local
development, and public client config does not expose local adapter state.

## API

Public:

- `GET /health`
- `GET /v1/health`
- `GET /v1/client-config`
- `GET /v1/errors`

Auth:

- `POST /v1/auth/register` when `SYSTEM_LOCKED=false`
- `POST /v1/auth/login`
- `POST /v1/auth/oauth`
- `POST /v1/auth/email/verify`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`
- `GET /v1/me`
- `DELETE /v1/me`

Authenticated data routes accept `Authorization: Bearer <jwt_access_token>`.
The bootstrap `API_KEY` is for admin/bootstrap workflows. Per-user API keys are
local-only by default; app clients should use JWT access tokens and rotating
refresh tokens.

- `POST /v1/chat` - preferred app surface for natural chat, journal saves,
  memory questions, article/document links, search, undo, and correction flows.
- `GET /v1/chat/conversations?page=1&limit=50`
- `GET /v1/chat/conversations/{conversation_id}/messages?page=1&limit=100`
- `POST /v1/entries`
- `POST /v1/entries/async`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs?page=1&limit=50&status=failed`
- `POST /v1/jobs/{job_id}/retry`
- `POST /v1/jobs/{job_id}/cancel`
- `GET /v1/entries?page=1&limit=50`
- `GET /v1/entries/{entry_id}`
- `GET /v1/entries/{entry_id}/status`
- `PATCH /v1/entries/{entry_id}/importance` - set a user-owned 1-5 importance rating or clear it with `null`
- `DELETE /v1/entries/{entry_id}`
- `GET /v1/ask?q=...`
- `POST /v1/library`
- `GET /v1/library`
- `GET /v1/library/{source_ref}`
- `GET /v1/status`
- `GET /v1/health/deep`
- `GET /v1/metrics`
- `GET /v1/people/{name}`
- `GET /v1/places/{name}`
- `GET /v1/reports`
- `GET /v1/graph`
- `GET /v1/context`
- `GET /v1/export`
- `GET /v1/account/export`
- `POST /v1/export/obsidian`
- `POST /v1/export/vault?zip=true`
- `GET /v1/personality`

Use `/v1/chat` for normal web/mobile UX. It now persists durable conversation
threads and pending confirmations, so web/mobile clients can restore transcript
history and confirm risky natural actions such as undo without relying on
in-memory state. The explicit `/v1/entries`, `/v1/library`, and `/v1/ask`
endpoints remain stable for power/debug flows.

Clear first-person experiences, reflections, plans, reminders, and ideas are
automatically routed into journal ingestion; no slash command is required.
Saved entries may be rated from 1 to 5 in web and native clients, or naturally
with phrases such as "rate that five stars" and "undo that rating". This is an
optional preference signal, not a truth score: it has a bounded effect on recall
tie-breaking and a stronger effect on recap ordering. Optional post-save rating
prompts are disabled by default and can be enabled in preferences. The plain
`importance` property survives Obsidian vault export and import.
Questions and ordinary conversation remain chat turns. When classification is
ambiguous, Thought Pins replies as chat and exposes a save hint instead of
silently creating a durable journal memory.

Private-memory recall is off by default. The **Use private memories** chat
control allows entries already marked private to inform a reply; it does not
mark the outgoing message private. When the control is off, private memories
stay out of search and answer context. The server enforces `PRIVATE_ALLOW_LLM`,
and an account-level preference can set the default while an individual request
may opt out. Private entry text is encrypted at rest when
`DATA_ENCRYPTION_KEY` is configured.

The initial public release is free. No subscription, in-app purchase, external
checkout, advertising, or paid SDK is shipped; `scripts/check_free_launch.py`
enforces the release contract in `deploy/store/commerce-policy.json`.


## Obsidian-Compatible Vault Import and Export

Thought Pins keeps SQL, vector, and graph memory systems as internal retrieval infrastructure. The human-readable notes layer is exported as a normal Obsidian-compatible vault folder: Markdown files, typed YAML properties, native Bases, a JSON Canvas memory map, safe Windows filenames, and wikilinks such as `[[People/Maya]]`. The compatibility target is the official Obsidian GitHub organization and Help docs at https://github.com/obsidianmd and https://help.obsidian.md/. The complete versioned contract is in `docs/architecture/OBSIDIAN_INTEROPERABILITY.md`.

Default layout:

- `Vault Home.md`
- `Journal/YYYY/MM/YYYY-MM-DD.md`
- `Entries/YYYY/MM/DD/<timestamp>-<title>.md`
- `People/`, `Places/`, `Organizations/`, `Projects/`, `Concepts/`
- `Library/Articles/`, `Library/Documents/`
- `Attachments/`, `_Indexes/`, `_Views/`, `_System/`
- `_Views/` contains four native `.base` views and `Memory Map.canvas`.
- Optional `.obsidian/` JSON defaults when `--obsidian-defaults` is requested; no community plugins are required.

Export the local default user's vault:

```powershell
python scripts/export_vault.py --zip
python scripts/export_vault.py --zip --obsidian-defaults
python scripts/validate_vault.py .\vault\<user_id>
python scripts/probe_obsidian_vault.py .\vault\<user_id>
python scripts/probe_obsidian_vault.py .\vault\<user_id> --cli --cli-vault-name "<vault-name>" --json
```

Open the exported folder directly in Obsidian with "Open folder as vault". If Obsidian is installed locally, `scripts/probe_obsidian_vault.py <vault> --open` can hand the folder to Obsidian through the local `obsidian://open?path=...` URI after validator checks pass. The probe records executable/protocol discovery, Obsidian process presence, and any vault-local `.obsidian` JSON settings created during the handoff. Entity notes and library notes include table-style cards for fast scanning, while original journal/source text is fenced so accidental `[[wikilinks]]` inside pasted material do not become broken notes.

Authenticated clients can download the same package from
`GET /v1/export/vault/download` and upload a ZIP to
the resumable `/v1/import/obsidian/uploads` workflow. Clients stage verified
chunks, preview new and changed notes, then explicitly apply or cancel the
tenant-scoped import. Interrupted uploads resume from the last committed byte;
the bounded `POST /v1/import/obsidian` endpoint remains for compatibility and
dry-run tooling. Auto mode classifies notes in Journal, Diary, Daily
Notes, or explicitly journal-tagged folders as journal memories and stores all
other Markdown notes as library sources. This boundary keeps research notes
recallable without presenting them as events the user lived. A Thought Pins
export is recognized by its manifest; only original entry and library notes are
re-imported, while generated indexes, daily rollups, entity cards, and event
cards, Bases, and the generated memory Canvas are skipped. User-authored Canvas
files become bounded library sources; Base files remain structural and are not
ingested as content. Imports are tenant scoped, idempotent by path and content,
preserve journal dates, and reject encrypted members, links, traversal paths,
oversized members, and unsafe compression ratios. Attachments are currently
reported and skipped; Markdown remains the portable source of truth.

Incremental export uses `_System/thoughtpins-export-state.json` as a hash
ledger for files generated by Thought Pins. It updates untouched generated
notes, removes only unchanged stale generated files, preserves custom notes,
and treats edited generated files as conflicts unless overwrite is explicitly
selected. A 2026-07-19 scale rehearsal exported and validated 10,000 entries
with zero findings and previewed a 100,000-note ZIP with no database writes;
the reproducible harness is `scripts/benchmark_vault_scale.py`.

Stress-test the vault exporter with legal public sources:

```powershell
python scripts/stress_vault_obsidian.py --max-source-chars 50000 --json
python scripts/stress_vault_obsidian.py --max-source-chars 30000 --obsidian-defaults --open-obsidian --json
python scripts/stress_vault_obsidian.py --offline-fixture --obsidian-defaults --with-container --json
```

The stress harness creates a temporary SQLite database, imports a public corpus, exports a vault and zip, validates the vault, runs an isolated Markdown/frontmatter/zip round trip, optionally opens Obsidian, and deletes the temporary database/vault by default. The live corpus currently includes three Sherlock Holmes public-domain books from Project Gutenberg, `Meditations`, `A Modest Proposal`, and two official Obsidian Help articles from `obsidianmd/obsidian-help`. Use only public-domain, permissively licensed, user-provided, or official free public-web sources for this harness; do not use pirated books, defeated access controls, or copyrighted source dumps.

Known limits: rendered desktop state still requires Obsidian itself. Obsidian 1.12.7+ provides an optional CLI that can read, search, query the generated Base, report unresolved links, inspect developer errors, and capture a screenshot while Obsidian is running. Earlier installs use validator success plus URI handoff/process detection. Docker/container checks are optional; if Docker is installed but the daemon is unavailable, the script records `container_check.status = unavailable` and relies on the local isolated parser check.

## Production Personality Modes

Only public-safe modes are active:

- `friendly`
- `clear`
- `mirror`

Response style is independent of voice-note capture. The public distribution
transcribes user-initiated recordings and then discards the audio. Optional
encrypted audio retention is a private/self-hosted deployment feature, is off by
default, and requires separate versioned consent from each user.

## Current Production Gaps

Still required before a serious multi-user launch:

- The exact local Compose topology has passed non-owner PostgreSQL RLS,
  Redis/Celery dispatch, authenticated shared-Qdrant recovery, PostgreSQL and
  vault restore drills, and a 100-VU health load. Repeat the same proof against
  the chosen managed staging services; local containers do not prove cloud
  networking, failover, or provider quotas.
- Configure real Google/Apple client IDs and decide whether OAuth registration
  is open or invite-only. Use a funded inference account for the end-to-end
  staging smoke; infrastructure health alone is not a successful AI workflow.
- Run the authenticated app-flow and chaos tests against staging, then repeat
  point-in-time recovery, vector snapshot restore, and log-redaction review
  before public signup.
- Choose a deployment target and adapt the templates in `deploy/`.

See [PRODUCTION_PLAN.md](docs/operations/PRODUCTION_PLAN.md) and
[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) for the detailed build order,
[TECHNICAL_REVIEW_GUIDE.md](docs/architecture/TECHNICAL_REVIEW_GUIDE.md) for a
reviewer-oriented code tour and verification path,
[PRODUCTION_RUNBOOK.md](docs/operations/PRODUCTION_RUNBOOK.md) for deploy, rollback, backup,
restore, and launch checks, [MOBILE_API_CONTRACT.md](docs/architecture/MOBILE_API_CONTRACT.md)
for the iOS/Android API contract,
[PRIVACY_AND_STORE_READINESS.md](docs/release/PRIVACY_AND_STORE_READINESS.md) for App Store
and Play Store readiness, and
[BACKEND_RELEASE_CHECKLIST.md](docs/operations/BACKEND_RELEASE_CHECKLIST.md) for the backend
release gate. See [WEB_APP_RELEASE_CHECKLIST.md](docs/operations/WEB_APP_RELEASE_CHECKLIST.md)
for the backend-served web app, [APP_CORE_FOUNDATION.md](docs/architecture/APP_CORE_FOUNDATION.md)
for UI-free app primitives, and [RELEASE_VERSIONING.md](docs/release/RELEASE_VERSIONING.md)
for backend, web, iOS, and Android versioning. See
[PLATFORM_CODEBASE_STRATEGY.md](docs/architecture/PLATFORM_CODEBASE_STRATEGY.md) for the web,
iOS, Android, and GitHub repo strategy. Founder/private operations are siloed in
[founder/](founder/README.md). The complete native release procedure is in
[MACOS_XCODE_APP_STORE_RUNBOOK.md](docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md),
with the first-Mac execution sequence in
[MAC_XCODE_V1_EXECUTION_CHECKLIST.md](docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md).

## License

Thought Pins is licensed under Apache-2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). Product names and marks are not granted by the software
license.
