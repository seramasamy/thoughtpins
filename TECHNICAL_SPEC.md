# Thought Pins Technical Specification

## Runtime Architecture

```text
clients
  -> backend-served web client (`frontend/static`, mounted at `/app`)
  -> FastAPI (`thoughtpins.api`)
      -> SQLAlchemy session (`thoughtpins.store`)
      -> relational schema (`thoughtpins.db`)
      -> auth/session helpers (`thoughtpins.auth`)
      -> ingestion jobs (`thoughtpins.jobs`)
      -> ingestion pipeline (`thoughtpins.ingestion`)
      -> memory/search/graph/report/export modules
      -> LLM client (`thoughtpins.llm.client`)
```

Optional adapter:

```text
Telegram polling (`thoughtpins.bot.telegram_app`)
  -> same ingestion and query modules
```

Telegram is disabled by default and should remain an adapter, not the product
surface.

## Package Layout

```text
src/thoughtpins/
  api.py                  FastAPI app and /v1 routes
  article_fetch.py        URL validation and local/Jina/Firecrawl/Apify fetch providers
  auth.py                 password hashing, JWT access tokens, refresh sessions
  config.py               environment config
  data_lifecycle.py       account export and deletion helpers
  db.py                   SQLAlchemy models
  email_verification.py   optional email verification token lifecycle
  jobs.py                 ingestion job tracking and local background runner
  oauth.py                Google/Apple OIDC ID token verification
  rate_limit.py           Redis-backed rate limiter with memory fallback
  reading_analysis.py     deterministic publisher/topic/concept extraction for sources
  runtime_health.py       deep dependency health checks
  store.py                engine/session/init helpers
  worker.py               Celery worker entry point for external queues
  server.py               process entry point
  users.py                API-key users and Telegram binding helpers
  bot/                    optional Telegram adapter and conversation commands
  backup.py               local backup/restore helpers for founder operations
  ingestion/              classification, extraction, normalization, entity resolution
  llm/                    provider-neutral OpenAI-compatible client and JSON repair
  memory/                 store, search, graph, vector adapter, reindex, corrections, maintenance
  vault/                  Obsidian-compatible Markdown vault rendering, packaging, validation
  obsidian/               compatibility shim for older export imports
  reports/                reports, charts, graph visualizations
frontend/static/
  index.html              zero-build web shell served by FastAPI at /app
  app.js                  browser client for auth, entries, jobs, ask, export
  styles.css              responsive app UI styles
```

## Configuration

Configuration comes from environment variables and optional `.env`.

Important variables:

- `ENVIRONMENT`: `development`, `staging`, or `production`.
- `REQUIRE_API_AUTH`: require API key auth for data routes.
- `API_KEY`: bootstrap/admin API key.
- `ALLOW_USER_API_KEYS`: local compatibility switch for permanent per-user API
  key auth; false in production.
- `RETURN_API_KEY_ON_REGISTER`: local compatibility switch; false in production
  so app users receive sessions through login/OAuth instead of permanent keys.
- `JWT_SECRET`: signing secret for access tokens.
- `ACCESS_TOKEN_EXPIRE_MINUTES` and `REFRESH_TOKEN_EXPIRE_DAYS`: session
  lifetimes.
- `DATABASE_URL`: SQLite for local dev, `postgresql+psycopg2://...` for current PostgreSQL path.
- `AUTO_CREATE_TABLES`: true only for local development.
- `REDIS_URL`: rate limiting and deep health.
- `RATE_LIMIT_AUTH_PER_MINUTE`, `RATE_LIMIT_INGEST_PER_MINUTE`,
  `RATE_LIMIT_LLM_PER_MINUTE`, `RATE_LIMIT_EXPORT_PER_MINUTE`, and
  `RATE_LIMIT_ACCOUNT_PER_MINUTE`: endpoint-specific rate limits.
  Staging/production return a retryable `503` when Redis cannot enforce the
  distributed limit; in-memory fallback is restricted to local development.
- `PROCESS_ENTRIES_ASYNC`: queue entry ingestion behind job status instead of
  blocking the request.
- `INGESTION_QUEUE_BACKEND`: `thread` for local, `celery` for production.
- `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`: Celery worker queue config.
- `CELERY_WORKER_CONCURRENCY` and `CELERY_QUEUE_NAME`: worker process sizing
  and queue routing.
- `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`: provider-neutral
  OpenAI-compatible LLM path. Local founder/dev endpoints are supplied through
  generic `LLM_*` settings, and runtime modules call `thoughtpins.llm.client`.
- `LLM_EXTRACTION_MODEL`: cheaper/faster model used for structured extraction;
  keep long-context chat on `LLM_MODEL`.
- `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_EMPTY_RESPONSE_RETRIES`, and
  `LLM_EXTRACTION_MAX_TOKENS`: timeout, retry, and bounded JSON extraction
  behavior. Structured extraction disables provider-specific thinking mode;
  normal chat can still use configured thinking/reasoning settings where
  supported.
- `MEMORY_CONTEXT_MODE`: `smart` by default; `full` forces exhaustive context
  packages for all chat/query answers.
- `MEMORY_CONTEXT_MAX_CHARS`: maximum generated prompt context budget.
- `MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS`: small-library threshold where smart
  mode still includes the full structured database.
- `MEMORY_CONTEXT_RELEVANT_MEMORIES`, `MEMORY_CONTEXT_RECENT_MEMORIES`, and
  `MEMORY_CONTEXT_RECENT_ENTRIES`: smart context selection limits.
- `LLM_HEALTHCHECK_LIVE`: opt-in live LLM call from deep health.
- `VECTOR_MODE`: `qdrant_local` for founder development or `qdrant_remote`
  for staging/production. In-memory, FAISS, and Chroma modes are test/dev only.
- `QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_TIMEOUT_SECONDS`: shared vector
  service connection settings required outside local development.
- `VECTOR_HEALTHCHECK_LIVE`: vector initialization/count check; required in
  staging and production.
- `SECURITY_HEADERS_ENABLED` and `MAX_REQUEST_BODY_BYTES`: HTTP hardening.
- `DATA_ENCRYPTION_KEY`: Fernet key required in production for private entries.
- `GOOGLE_OAUTH_CLIENT_IDS` and `APPLE_OAUTH_CLIENT_IDS`: comma-separated OIDC
  audiences for OAuth login.
- `REQUIRE_EMAIL_VERIFICATION`: optional email verification gate.
- `SENTRY_DSN`: optional crash reporting.
- `ENABLE_TELEGRAM_BOT`: opt-in legacy adapter.
- `TELEGRAM_ALLOWED_USER_IDS`: required when Telegram is enabled.
- `TELEGRAM_TEST_MODE`: local-only first-user Telegram test allowlisting.
- `ENABLE_FOUNDER_MODE`: local-only founder test personality and `/founder`
  command.
- `CONFIDENTIAL_ACCESS_CODE`: required before Telegram confidential mode can be
  enabled.

Telegram bot startup uses `Config.validate_telegram_startup()` so missing tokens,
unsafe production test mode, missing founder access code, or missing allowlist
configuration fail before polling starts.

The current code uses synchronous SQLAlchemy. If `postgresql+asyncpg://` is
provided, config normalizes it to `postgresql+psycopg2://` until the async DB
layer is built.

## API Auth

Preferred authenticated routes use:

```http
Authorization: Bearer <jwt_access_token>
```

Auth endpoints:

- `POST /v1/auth/register` creates a user when `SYSTEM_LOCKED=false`.
- `POST /v1/auth/login` returns an access token and refresh token.
- `POST /v1/auth/oauth` verifies Google or Apple OIDC ID tokens and issues a
  Thought Pins session.
- `POST /v1/auth/email/verify` verifies optional email tokens.
- `POST /v1/auth/refresh` rotates refresh sessions and returns a new pair.
- `POST /v1/auth/logout` revokes a refresh token.

Refresh rotation consumes the old session with an atomic conditional update.
Concurrent uses of the same refresh token cannot both mint a successor.
Apple-backed account deletion revokes the encrypted provider refresh token
before local erasure. Failed remote revocation returns a retryable service
error and retains the credential so the required revocation can be retried.

For local bootstrap and migration workflows, routes can accept API keys:

```http
X-API-Key: <api_key>
```

or:

```http
Authorization: Bearer <api_key>
```

Production app clients should use JWT/OAuth sessions. Permanent per-user API
keys are disabled by default outside local development.

## Tenant Isolation

Tenant ownership columns now exist on:

- `raw_entries`
- `entities`
- `entity_mentions`
- `memories`
- `relationships`
- `events`
- `event_participants`
- `action_items`
- `expenses`
- `reports`
- `ingestion_jobs`
- `auth_sessions`
- `audit_logs`

The API resolves the authenticated user and passes `user_id` into ingestion,
memory queries, search, reports, graph exports, and Obsidian export.

Remaining work:

- Backfill old local rows with the intended default user.
- Verify PostgreSQL RLS policies against the exact non-owner production
  database app role.
- Add tenant-isolation tests for every endpoint and export path.

## Memory Context Engine

Question answering and Telegram conversation build a prompt context package from
the user's local database. The active mode is controlled by
`MEMORY_CONTEXT_MODE`.

- `smart`: default. Always includes the navigational memory map. If the library
  is below `MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS`, it also includes the full
  structured database. Once the library grows beyond that threshold, it includes
  query-relevant memories, recent memories, open action items, raw entry
  excerpts, recent expenses, relevant saved source/document excerpts, and exported vault text within
  `MEMORY_CONTEXT_MAX_CHARS`. Memory lines include stable memory ids and source
  provenance so retrieval can be debugged without exposing internals in normal
  answers.
- `full`: includes the navigational memory map plus the full structured
  database, truncated to fit the prompt budget.

Telegram exposes `/context` for the active mode, `/context why <question>` for
section-level diagnostics without memory text, `/ask` for the configured mode,
and `/askfull` for a one-off exhaustive audit. Founder Telegram mode should use
the same `smart` default as production so local testing exercises the real user
experience, while `/askfull` remains available for recall audits.

The navigational map must respect confidential mode. Private raw entries and
private-derived memories, relationships, events, action items, and expenses are
excluded unless the Telegram confidential mode is active.

Correction memories supersede stale facts. A correction stores a raw entry,
creates one or more `memory_type=correction` rows, sets `valid_to` on conflicting
old memories, and removes those stale facts from normal search/context. Raw old
entries remain available as historical source text, but active correction
memories win when there is a conflict.

## Reading/Document Memory

External content the user reads is stored separately from autobiographical
journal entries:

- `document_sources`: one row per URL, pasted article, or uploaded document.
- `document_chunks`: readable source text split for exact retrieval.
- `memories` with `memory_type=source_summary` and `source_excerpt`, linked by
  `source_provenance=document:<id>` and structured metadata.

Telegram commands `/read`, `/library`, and `/source` expose this flow. API
routes `/v1/library` mirror it for mobile/web clients. URL fetching only uses
the publicly accessible page response; publisher controls are respected. If text is not
available, the source is saved with `status=needs_text` and the user can paste
content they have access to.

Article/link ingestion uses explicit provenance fields on `document_sources`:
`original_url`, `canonical_url`, `source_domain`, `access_method`,
`rights_basis`, `fetch_status`, `paywall_detected`, and
`retrieval_quality_score`. The default provider list is `local`, which performs
a normal HTTP fetch and local readable-text extraction. Optional public-page
reader providers can be enabled with `ARTICLE_FETCH_PROVIDERS=local,jina,firecrawl`
for the default public-link path: normal HTTP extraction first, Jina Reader as
the cheap markdown reader, and Firecrawl for JavaScript-heavy public pages. Use
`ARTICLE_FETCH_PROVIDERS=local,jina,firecrawl,apify` when Apify is explicitly
configured as a specialist fallback. Firecrawl requires `FIRECRAWL_API_KEY`. Apify requires
`APIFY_API_TOKEN` and `APIFY_READER_ACTOR`; `APIFY_READER_INPUT_TEMPLATE` can
adapt Thought Pins to a chosen actor's input schema. Private/local URLs are blocked unless
`ARTICLE_ALLOW_PRIVATE_URLS=true` in non-production local development.

On successful or metadata-only ingestion, `metadata_json.reading_analysis`
stores the inferred publisher label, source domain, title, author/date when
available, detected topics, key concepts, and word count. The memory layer then
creates both `source_summary` and `source_characteristics` memories before
chunk memories. This gives chat/query retrieval a compact "read list" index
plus full-text evidence chunks.

If a URL is inaccessible but the same message contains a long pasted article,
the pasted text is stored as `access_method=user_paste` and
`rights_basis=user_provided`, while original fetch metadata is preserved.
Optional document graph enrichment can be enabled with
`LIBRARY_EXTRACT_GRAPH=true`; SQL document/source rows remain the source of
truth and graph extraction failure never makes ingestion fail.

## Memory Retrieval Infra

Thought Pins' default retrieval stack is local-first and source-of-truth-safe:

- exact phrase search over active memories;
- BM25-style lexical scoring over memories and raw entries, with rare-token,
  exact-phrase, and token-proximity signals so obscure exact details outrank
  generic overlap;
- tenant-filtered dense vector search through the configured vector store;
- document/source title and summary retrieval;
- SQL graph expansion from matched entities through typed relationships;
- context composition with separate sections for query-relevant memories,
  selected recent memories, graph/source evidence, raw excerpts, open actions,
  expenses, and exported vault files.

The ranking pipeline is intentionally inspectable. Query analysis extracts a
normalized token sequence, high-value identifiers, quoted phrases, phrase
fragments, and a bounded specificity estimate. Candidate generation can come
from SQL, vectors, graph traversal, raw entries, or documents; final ranking
uses reciprocal-rank fusion to combine those incompatible score scales, then
adds calibrated lexical, phrase, proximity, source-consensus, temporal, and
source-kind signals. A maximal-marginal-relevance pass packs the final context
so the assistant gets both the best match and enough diversity to avoid filling
the prompt with repeated near-duplicates. Each returned `SearchResult` carries
`ranking_signals` for debugging retrieval failures without exposing private
memory text in health checks.

`GRAPH_PROVIDER=internal_sql` is the default. A pluggable graph backend adapter
can run Graphiti as an optional auxiliary backend via `GRAPH_SHADOW_ENABLED=true`
after installing the `graph` extra and configuring the desired Graphiti driver.
The SQL graph remains authoritative until evals prove Graphiti improves recall
and until data lifecycle operations are verified against the chosen graph
backend. Production validation rejects external graph and shadow modes while
that tenant deletion proof is incomplete.

`/audit` and `/v1/memory/audit` check memory quality, duplicate entities,
ontology-invalid relationships, metadata-only sources, missing chunks, stale
jobs, and graph-backend status. `scripts/evaluate_memory_infra.py` runs a
deterministic benchmark covering obscure recall, document recall, graph entity
bridging, multi-hop retrieval, and context composition.

## Memory Maintenance

Derived vector search can be rebuilt from the relational database:

```powershell
python scripts/reindex_vectors.py --verify-query "some remembered detail"
python scripts/memory_maintenance.py --reindex
python scripts/evaluate_memory_quality.py
```

`thoughtpins.memory.reindex.reindex_vectors()` is the shared service used by the
Telegram `/reindex` command and CLI scripts. It indexes only active memories
(`valid_to IS NULL`) and preserves tenant isolation by always treating the
database as the source of truth. The vector layer also filters candidates by
`user_id`, and each supported backend implements point deletion. In-memory and
FAISS indexes rebuild their retained set; Chroma and Qdrant delete explicit IDs.
The API and worker share an authenticated remote Qdrant service in production;
local Qdrant is deliberately limited to founder/developer operation. Account
deletion cleans the derived index before relational erasure and fails retryably
without deactivating the account if that cleanup cannot be confirmed.
Tenant write transactions coordinate on the active user row (`FOR SHARE`),
while deletion holds `FOR UPDATE` through cleanup. Long-running ingestion
rechecks the active account under that lock before committing extracted data.
Qdrant point deletion spans all application-owned dimension collections;
unexpected production dimension drift is an operator-visible failure rather
than an implicit reset. A controlled reindex is the only promotion path.
`thoughtpins.memory.maintenance` adds stale job recovery and duplicate-entity
diagnostics.

## Database

Local development:

```env
DATABASE_URL=sqlite:///./data/thoughtpins.sqlite3
AUTO_CREATE_TABLES=true
```

Production target:

```env
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/thoughtpins
AUTO_CREATE_TABLES=false
```

`create_all()` is retained only for local development. Production must use
Alembic migrations.

Production should use two PostgreSQL roles:

- Migration role: owns schema objects and runs Alembic.
- App role: receives table privileges but does not own RLS-protected tables.

Run `scripts/verify_postgres_rls.py` with `DATABASE_URL` set to the migration
role and `RLS_VERIFY_DATABASE_URL` set to the app role.

Migration commands:

```powershell
alembic upgrade head
alembic downgrade -1
```

## API Routes

Public:

- `GET /`
- `GET /health`
- `GET /v1/health`
- `GET /v1/errors`
- `POST /v1/auth/register` when `SYSTEM_LOCKED=false`
- `POST /v1/auth/login`
- `POST /v1/auth/oauth`
- `POST /v1/auth/email/verify`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`

Authenticated:

- `GET /v1/health/deep`
- `GET /v1/status`
- `POST /v1/chat`
- `GET /v1/chat/conversations`
- `GET /v1/chat/conversations/{conversation_id}/messages`
- `POST /v1/entries`
- `POST /v1/entries/async`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs`
- `POST /v1/jobs/{job_id}/retry`
- `POST /v1/jobs/{job_id}/cancel`
- `GET /v1/entries`
- `GET /v1/entries/{entry_id}`
- `GET /v1/entries/{entry_id}/status`
- `DELETE /v1/entries/{entry_id}`
- `GET /v1/ask`
- `POST /v1/library`
- `POST /v1/uploads`
- `GET /v1/library`
- `GET /v1/library/{source_ref}`
- `POST /v1/import/obsidian`
- `GET /v1/people/{name}`
- `GET /v1/places/{name}`
- `GET /v1/reports`
- `GET /v1/graph`
- `GET /v1/graph/html`
- `POST /v1/export/obsidian`
- `POST /v1/export/vault?zip=true`
- `GET /v1/export/vault/download`
- `GET /v1/export`
- `GET /v1/account/export`
- `GET /v1/me`
- `DELETE /v1/me`
- `GET /v1/personality`
- `GET /v1/context`

Legacy aliases such as `/ingest`, `/ask`, `/person/{name}`, and `/report` are
kept for local compatibility.

`POST /v1/chat` is the preferred web/mobile surface. It uses the same routing
engine as Telegram for natural chat, journal saves, memory questions,
article/document ingestion, undo, and correction-like requests. Chat turns are
stored in `chat_conversations` and `chat_messages`; risky natural actions are
stored in `pending_chat_actions` until confirmed, canceled, or expired. These
tables are user-scoped, included in export/delete/reset flows, and covered by
PostgreSQL RLS migrations.

Obsidian ZIP import is implemented in `thoughtpins.vault.importer`. Archive
inspection is in-memory and bounded by compressed size, expanded size, member
count, member size, path depth, and compression ratio. It rejects traversal,
absolute paths, symbolic links, encrypted members, and non-UTF-8 Markdown.
Journal notes become durable ingestion jobs with forced journal routing,
path/content deduplication, and preserved source dates. Other notes use normal
library ingestion with source path, frontmatter, and wikilink provenance. A
Thought Pins manifest activates lossless original-text sections and suppresses
derived note duplication.

## Release Tooling

- `scripts/export_openapi.py --check` validates and exports the OpenAPI contract.
- `scripts/export_vault.py --zip [--obsidian-defaults]` exports a user vault folder/zip that can open directly in Obsidian; optional defaults write plugin-free `.obsidian` JSON for attachment path, core plugins, appearance, and daily notes.
- `scripts/validate_vault.py <vault>` verifies frontmatter, paths, wikilinks, empty notes, and secret leakage.
- `scripts/probe_obsidian_vault.py <vault> [--open]` validates and optionally hands a vault folder to a local Obsidian install, then reports process/config evidence.
- `scripts/stress_vault_obsidian.py` creates a temporary DB, imports a legal public corpus, exports/validates/zips a vault, runs isolated Markdown/YAML/zip compatibility checks, optionally writes `.obsidian` defaults, optionally opens Obsidian, optionally attempts a Docker parser check, and cleans temp state by default.
- `scripts/smoke_api.py` runs auth, health, entry, jobs, entries, export, and
  optional cleanup against a running API.
- `load/k6-health.js` checks health endpoint latency.
- `load/k6-api-flow.js` exercises the app-grade auth/entry/job/list flow.
- `deploy/` contains Fly.io and Railway templates for API and worker processes.

## Logging And Monitoring

Loguru writes stderr and daily rotating log files. `JSON_LOGS=true` serializes
logs for aggregation. `SENTRY_DSN` enables Sentry if `sentry-sdk` is installed.

Logging policy still needs hardening so raw journal text is not emitted by
errors, retries, or debug traces.

## Production Security Checklist

- [x] Remove hard-coded Telegram token and private user ID defaults.
- [x] Require explicit Telegram allowlist when Telegram is enabled.
- [x] Add app-level user scoping to API data paths.
- [x] Add JSON logging mode and optional Sentry initialization.
- [x] Add Alembic migration scaffolding and baseline migration.
- [x] Make tenant `user_id` non-null in the ORM schema.
- [x] Add JWT access/refresh tokens.
- [x] Add Redis-backed rate limiting.
- [x] Add account export/delete lifecycle.
- [x] Add focused tests for auth, user scoping, jobs, and account deletion.
- [x] Add PostgreSQL RLS migration artifact for journal-owned tables.
- [x] Add local-only founder Telegram test mode.
- [x] Add OAuth ID-token verification for Apple and Google.
- [x] Add request IDs, error envelopes, and Prometheus-style metrics.
- [x] Add Celery worker backend for production async extraction.
- [x] Add CI RLS verification path using a non-owner app role.
- [x] Add security headers, body limit, endpoint rate-limit tiers, and audit events.
- [x] Add mobile-friendly job list/retry/cancel endpoints.
- [x] Add deploy templates, OpenAPI export, Docker CI, and API flow smoke/load checks.
- [ ] Verify PostgreSQL RLS with the deployed non-owner app role.
- [ ] Add broad endpoint-by-endpoint tenant-isolation tests.
- [ ] Add load testing and deployment rollback docs.
