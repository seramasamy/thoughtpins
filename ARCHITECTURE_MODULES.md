# Thought Pins Module Map

This codebase is organized as gears with stable boundaries. New work should
extend the owning gear first and only touch the API or Telegram command surfaces
as thin adapters.

## Core Gears

- `api.py`: FastAPI app wiring, middleware, auth dependencies, and legacy
  route adapters that have not yet been split. Keep business logic out of this
  file; route handlers should delegate.
- `api_routes/`: split FastAPI routers. `metadata.py` owns health, client
  config, error catalog, metrics, and deep health routes. `public.py` owns
  public legal pages and backend-served web app files. `auth.py` owns
  registration, password auth, OAuth, email verification, refresh, and logout.
  `entries.py` owns entry ingestion, entry listing/detail/status/delete, and
  ingestion job listing/retry/cancel/status.
- `api_memory_cards.py`: typed source/card response schemas and database-to-API
  projections for people, places, events, concepts, and source provenance.
- `demo/`: deterministic, clearly fictional reviewer corpus and idempotent
  local seeding. Product routes never depend on demo code.
- `chat/`: durable chat execution, pending actions, natural command execution,
  bounded adapter history, provider-independent fallbacks, and deterministic
  context-budget projection.
- `chat/importance_actions.py`: natural-language rating and rating-preference
  commands. The main action dispatcher owns routing; this module owns the
  importance transaction and response contract.
- `ingestion/`: message classification, structured memory extraction,
  normalization, entity resolution, and storage pipeline. `service.py` owns
  the ingestion transaction and failure policy; `storage.py` owns typed
  extraction persistence. `pipeline.py` remains the stable public adapter.
- `ingestion/extraction_recovery.py`: bounded semantic retry and a
  source-preserving memory fallback for syntactically valid but empty provider
  output. It never infers entities or relationships.
- `ingestion/entity_type_correction.py`: deterministic type repair plus bounded
  contextual review for suspicious people. Its provider factory is injected,
  and the reserved journal-owner anchor cannot be retyped.
- `ingestion/explicit_facts.py`: conservative deterministic recovery for
  explicit currency amounts and direct reminder requests. It recognizes bounded
  natural word orders, named recipients, and clearly coordinated verb tasks;
  reported speech and negated requests remain excluded. Ambiguous interpretation
  stays in the structured extraction layer.
- `ingestion/classify.py`: phase-ordered deterministic routing with a bounded
  provider fallback. Override, command, URL, conversational, journal, and
  ambiguity phases are independently testable and preserve the public result
  contract.
- `memory/`: retrieval, hybrid ranking, graph backends, vector stores,
  maintenance, reset, audit, and eval harnesses.
- `memory/search.py`: candidate generation only. Each channel is a `_collect_*`
  function that proposes into a shared map; the orchestrator absorbs any one of
  them failing, because a channel is an optimisation and not a dependency.
  Candidate identity must be deterministic across processes — derive it from
  content with a stable digest, never `hash()`, or replayable evaluation and
  any cache keyed on a candidate break silently.
- `memory/ranking.py`: pure candidate scoring and reranking policies. A ranking
  policy can be replayed over a fixed candidate pool, which makes ablation
  results reproducible without provider or database variance. Every coefficient
  belongs in `RankingWeights` with a declared upper bound; a literal left inside
  the scorer is a hyperparameter hidden from ablation and validation.
- `memory/social_relevance.py`: deterministic query-facet and social-scene
  features, including attribution and factualization-risk handling.
- `memory/evidence_plan.py`: compact provenance-aware response planning between
  retrieval and synthesis. It never executes stored content or changes data.
- `memory/social_benchmark.py` and `memory/public_domain_eval.py`: disposable
  evaluation-only workloads. They cannot write to product memory or vaults.
- `memory/benchmark_datasets.py`, `memory/longmemeval_benchmark.py`, and
  `memory/litbank_benchmark.py`: licensed external-corpus verification,
  deterministic partitions, and independently labeled retrieval evaluation.
- `memory/benchmark_retrieval.py`: dependency-free BM25 baseline and aggregate
  IR metrics shared by external adapters.
- `memory/context_scope.py`, `memory/context_sections.py`, and
  `memory/context_package.py`: tenant scoping, deterministic full/navigation
  sections, and bounded smart-context orchestration respectively.
- `memory/evaluation_cases.py`: stable, human-labeled retrieval judgments.
  Labels describe relevance independently from the signals used by the
  ranker, so evaluation does not reward its own heuristics.
- `memory/evaluation_metrics.py`: source-deduplicated precision, recall, MAP,
  reciprocal rank, nDCG, evidence coverage, and score-margin measurement.
  Duplicate lexical, vector, and graph paths to one source count once.
- `memory/evaluation_fixture_store.py`: deterministic SQL fixture builders used
  by evaluation code; serving modules must not import it.
- `memory/salience.py`: pure, deterministic entry/entity prominence model.
  `memory/salience_store.py` owns tenant-scoped evidence aggregation,
  versioned persistence, backfills, and refreshes after rating or deletion;
  `memory/salience_evidence.py` projects typed SQL evidence into the pure model.
- `library.py`: document/source persistence and conversion into memories.
  `library_text.py` owns pure cleaning, chunking, title, summary, and raw-entry
  rendering primitives so transport and persistence code do not duplicate them.
- `article_fetch.py`: URL validation, local/Jina/Firecrawl/Apify provider
  fallbacks, fetch diagnostics, and provider compliance behavior.
- `reading_analysis.py`: deterministic publisher, topic, concept, and word-count
  analysis for saved reading sources.
- `runtime_health.py`: deep runtime dependency checks for LLM, embeddings,
  article fetch providers, Redis, workers, graph backend, DB, and job backlog.
- `llm/`: provider-neutral OpenAI-compatible LLM client and JSON repair.
- `backup.py` and `backup_provenance.py`: archive creation/restore and adjacent
  integrity/recovery metadata. Restore verifies available SHA-256 sidecars
  before extracting an archive.
- `bot/`: Telegram adapter. Telegram should call the same core gears as web/API,
  not implement separate product logic.
- `bot/reading_commands.py`: Telegram adapter for `/read`, natural article
  ingestion, `/library`, and `/source`; keep article-product behavior here
  thin and delegate persistence/fetching to `library.py` and `article_fetch.py`.
- `bot/memory_commands.py`: Telegram adapter for `/today`, `/week`,
  `/recent`, `/search`, and `/memory`; keep retrieval behavior in
  `memory/search.py` and summary/digest generation in `reports/`.
- `bot/ops_commands.py`: Telegram adapter for `/status`, `/doctor`, `/audit`,
  `/jobs`, and `/backup`; keep health/report construction in `founder/`,
  `memory/audit.py`, and `backup.py`.
- `bot/help_command.py`: optional Telegram command reference and live privacy/
  personality state. The primary product path remains command-free chat.
- `bot/entity_commands.py`: Telegram adapter for `/person`, `/place`,
  `/people`, `/places`, `/concepts`, `/rename`, `/forget`, and `/merge`; keep
  entity lookup, alias handling, reference counting, and safe cleanup here.
- `bot/utils.py`: shared Telegram adapter helpers for chat/user resolution,
  limit parsing, and Telegram-safe message trimming.
- `founder/`: local founder diagnostics and operational summaries.
- `data_lifecycle.py`: user export and deletion.
- `vault/`: Obsidian-compatible human-readable vault rendering, optional
  plugin-free `.obsidian` defaults, export packaging, validation, and
  source-text escaping. Import orchestration is staged into request validation,
  package metadata, revision policy, journal queueing, library persistence, and
  dispatch helpers. Internal memory/vector/graph retrieval remains separate.
  `obsidian/` is a compatibility shim for older imports. `reports/` owns
  generated reports.
- `scripts/`: release gates, smoke tests, migrations checks, live evals, and
  maintenance entry points. Scripts should import core gears rather than
  reimplementing product behavior.
- `frontend/src/styles/`: ordered, token-driven style layers. Shared visual
  primitives, controls, feedback/data components, feature views, and
  responsive overrides remain separate so cascade ownership is explicit.

## Agent Rules

- Add provider-specific URL fetching in `article_fetch.py`.
- Add new API surfaces in `api_routes/` when they can be isolated without
  circular imports. Leave `api.py` as app wiring plus thin legacy adapters.
- Add article/read-list concepts in `reading_analysis.py`.
- Add document persistence or source-memory shape in `library.py`.
- Add Obsidian-compatible note layout, frontmatter, wikilinks, or vault validation in `vault/`, not in API, Telegram, or memory modules.
- Add Telegram reading UX in `bot/reading_commands.py`, not `bot/commands.py`.
- Add Telegram memory/search UX in `bot/memory_commands.py`, not
  `bot/commands.py`.
- Add Telegram operational/admin UX in `bot/ops_commands.py`, not
  `bot/commands.py`.
- Add Telegram entity graph UX in `bot/entity_commands.py`, not
  `bot/commands.py`.
- Use `bot/utils.py` for shared Telegram adapter helpers instead of creating
  command-local copies.
- Add candidate collection in `memory/search.py` and ranking-policy changes in
  `memory/ranking.py`. Add new judgments or metrics to their dedicated
  evaluation modules rather than embedding benchmark logic in either path.
- Add social query facets and epistemic feature extraction in
  `memory/social_relevance.py`; keep response formatting in
  `memory/evidence_plan.py`.
- Add importance and prominence math in `memory/salience.py`; keep database
  aggregation in `memory/salience_store.py`.
- Add LLM provider behavior in `llm/openai_compatible_client.py`.
- Add ingestion orchestration in `ingestion/service.py`, and add extraction-to-
  database projections in `ingestion/storage.py`. Preserve `pipeline.py` as a
  compatibility boundary for API, worker, Telegram, and tests.
- Add provider-output recovery in `ingestion/extraction_recovery.py`; add only
  syntax-level, high-precision fact recovery in `ingestion/explicit_facts.py`.
- Keep classification phase ordering in `ingestion/classify.py`; a new signal
  belongs in the narrowest phase that can decide it without provider inference.
- Keep salience math pure in `memory/salience.py`, SQL aggregation in
  `memory/salience_store.py`, and evidence projection in
  `memory/salience_evidence.py`.
- Add archive contents in `backup.py`; add checksum, sidecar, and verification
  behavior in `backup_provenance.py`.
- Add health diagnostics in `runtime_health.py`.
- Add reusable runtime checks in `scripts/` and keep them safe for Windows
  PowerShell, local SQLite, and local Qdrant file-lock constraints.
- Keep `api.py` and `bot/commands.py` as adapters. If a new route or command
  needs more than request parsing plus delegation, create or extend a core gear.

## Current Refactor State

The document/link ingestion path has been split into fetch, analysis, and
persistence gears. The human-readable notes export is now a first-class
Obsidian-compatible `vault/` gear with `obsidian/` left as an import shim.
Runtime health checks have been split out of `api.py`.
Memory-card response projection, account-preference resolution, and
reviewer-corpus seeding are now isolated from API composition and one-off
scripts. Telegram conversation persistence and vault projection now live in
the shared chat gear, and memory reset no longer imports the Telegram adapter.
Hybrid ranking is isolated from retrieval adapters, and its deterministic
evaluation separates labeled judgments, metric computation, and policy
ablation. This keeps a score change reviewable and prevents fixture-specific
logic from entering the serving path.
Architecture fitness is enforced by
`scripts/check_architecture_budget.py`: legacy concentrations may shrink but
cannot grow, and core memory layers cannot acquire new transport dependencies.
Telegram reading, memory/search, entity, and operational commands now live in
feature modules with shared adapter utilities. API health/metadata, public,
auth, and entries/jobs routes now live in `api_routes/`. The remaining large
adapter files are `api.py` and `bot/commands.py`; refactor those by feature
slice when changing their behavior, not through a broad mechanical move.
The ingestion transaction is similarly split from typed persistence while its
public call signature remains stable. Conversation caches are configurable and
live evaluations redirect every mutable store into disposable state, so a
quality rehearsal cannot contaminate a real user's memory.
