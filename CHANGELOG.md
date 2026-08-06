# Changelog

All notable changes to Thought Pins are documented here. The format follows
Keep a Changelog, and the project uses semantic versioning for public releases.

## [Unreleased]

### Added

- Edit and resend a chat turn. Rewinding a conversation discards the replies
  below it, as in any chat product; because a rewound turn may have saved a
  journal entry, retired turns are marked rather than deleted and any entries
  they wrote are reported so the interface can say what it kept.
- A private-launch invite wall with a throttled request queue and digest.
- Startup refuses voice retention on a shared deployment whose archive path is
  not durable, so consent to keep a recording cannot outlive the disk it is on.
- Public, content-minimal `/ready` and `/v1/health/ready` probes with bounded
  dependency evaluation and `503` fail-closed semantics for load balancers.
- Repeatable PostgreSQL logical dump/restore and authenticated multi-tenant
  load rehearsals, including cross-tenant probe denial, asynchronous queue
  drain, lifecycle cleanup, and deterministic JSON evidence.
- Scoped worker, Redis, PostgreSQL, and vector-service failure/recovery drills
  against the production-shaped local Compose topology.
- AES-256 private source backups with encrypted headers, a separately saved
  recovery key, outer checksum, embedded per-file manifest, and an independent
  full extraction verifier.
- Obsidian vault schema v2 with typed properties, four native Bases, a
  deterministic JSON Canvas memory map, Canvas-to-library import, and optional
  Obsidian CLI acceptance checks.
- Adjacent SHA-256 and private recovery sidecars for runtime and private source
  backups, with integrity verification before restore.
- Disposable evaluation-state isolation and a complete five-book Project
  Gutenberg retrieval regression covering duplicate import and tenant scope.
- A Mac/Xcode v1 execution checklist and signed-archive enforcement for native
  Google OAuth build identifiers.
- Durable Apple and Google OAuth account bindings with provider-subject hashing,
  encrypted Apple refresh tokens, nonce validation, and deletion-time revocation.
- Native Google sign-in wiring for Android and iOS source configuration.
- Reproducible Python dependency locks and stricter static-analysis gates.
- Social-episodic relevance scoring, provenance-aware response evidence plans,
  and claim lifecycle fields for attributed statements and corrections.
- Disposable 5,000-case contemporary social benchmark and a 300-book
  Project Gutenberg retrieval benchmark with source-header validation.
- Reproducible LongMemEval and LitBank adapters with pinned source manifests,
  license enforcement, deterministic train/validation/holdout partitions, a
  BM25 baseline, and MRR/nDCG/recall reporting.
- Python maintainability gate for UTF-8 encoding, high-confidence dead code,
  and a repository-wide cyclomatic-complexity ceiling of 30, with no
  grandfathered exceptions.

### Fixed

- Graph evidence carried a process-dependent identity, derived from Python's
  salted `hash()`. Candidate identity is now a content digest, which is what
  makes replaying an evaluation across runs meaningful.
- `memory.search` released a session only on the success path, and guarded only
  one of its eight retrieval channels against provider failure.
- The entity-resolution memo grew without bound in long-lived workers.
- LLM retries paused a constant interval, so a rate-limited provider was met
  with unchanging pressure and every worker returned to the wire together. Now
  exponential with full jitter.
- Public legal pages answered `401` when their URL carried a trailing slash,
  including the account-deletion page reached by people who cannot sign in.
- The mobile landing pages: an unswipeable card scrubber, a header that printed
  over headings, legal prose with no paragraph spacing, and touch targets
  between 23px and 41px.

### Changed

- Reranking derives query interpretation once per request instead of once per
  candidate, roughly halving rerank latency with byte-identical output.
- All nineteen ranking coefficients are declared and bounded in one validated
  structure; adding one without a bound now fails construction.

#### Earlier in this cycle

- Replaced the worker image's inherited API health probe with process-and-broker
  health checks and made Compose worker concurrency configurable.
- Made person-type correction conservative for multi-part names and preserved
  otherwise valid structured memories when an inference provider emits a null
  claim status.
- Verified the vault contract against Obsidian Desktop 1.12.7 and made the
  Windows CLI probe decode UTF-8 explicitly so Unicode names survive evidence
  capture and Base-query assertions.
- Split the ingestion transaction from typed extraction persistence while
  preserving the stable pipeline adapter used by API, worker, and Telegram.
- Made authorization, billing, and permission failures from a configured LLM
  fail immediately instead of consuming retry budget; retryable transport and
  service failures retain bounded backoff.
- Made refresh-token rotation an atomic compare-and-set operation, with an
  adversarial simultaneous-refresh test that proves one-time consumption.
- Added tenant filtering inside vector candidate generation and complete
  deletion behavior for in-memory, FAISS, Chroma, and Qdrant-derived indexes.
- Made asynchronous ingestion a database-backed outbox: broker publication is
  retryable, worker claims are atomic, stale queue handoffs carry an explicit
  timestamp, and the worker periodically relays recoverable jobs.
- Split vector deployment modes explicitly: founder development may use a
  local Qdrant index, while staging and production require an authenticated
  shared Qdrant service with live health verification.
- Made account deletion fail closed and remain retryable when the derived
  vector store cannot confirm cleanup, instead of reporting partial erasure.
- Coordinated account erasure with in-flight chat, journal, and document writes
  through PostgreSQL user-row locks and an active-state recheck before final
  ingestion commits.
- Extended Qdrant erasure across every application-owned embedding-dimension
  collection and made unexpected production dimension drift fail closed until
  a controlled reindex is run.
- Made failed Sign in with Apple token revocation retryable: local account and
  encrypted credential deletion no longer proceed when a remote revocation
  attempt fails.
- Kept external graph adapters evaluation-only in production until their
  tenant deletion lifecycle is verified.
- Removed an unused memory-provider prototype and excluded generated
  `*.egg-info` metadata from sanitized source archives.
- Strengthened mypy across every explicitly targeted project module with
  unreachable, redundant-cast, optional, equality, and stale-suppression
  diagnostics while excluding third-party implementation internals.
- Canonicalized the Python tree with Ruff formatting and made formatting a
  required CI and local-release invariant.
- Split pure lexical query analysis from SQL-backed retrieval orchestration.
- Hardened native session refresh, local logout, no-store networking, and safe
  API error handling.
- Made Android account selection handle missing credentials and cancellation
  explicitly, with a lint-clean Fragment compatibility floor.
- Expanded hybrid retrieval coverage for rare terms in long memory collections.
- Made the public-domain benchmark repair legacy Windows newline expansion,
  write normalized cache files atomically, and fail on partial requested samples.
- Added fail-fast release-environment preflight, exact architecture size
  ratchets, and allowlisted cleanup of generated review artifacts.
- Upgraded contextual prominence to `salience-v4`, bounding star influence by
  query relevance and adding causal, attributed, unresolved, and social-scene
  signals.
- Made structured extraction request provider-neutral JSON-object mode with a
  plain compatibility fallback, maintained syntax repair, and complete partial
  recovery of provenance-bearing fields.
- Added a bounded semantic retry for structurally empty extraction responses,
  a source-preserving final fallback, and high-precision recovery of explicit
  expenses and direct reminder requests, including named recipients and
  coordinated tasks without interpreting reported speech.
- Split deterministic evaluation persistence helpers from scoring orchestration
  to keep benchmark code inside architecture budgets.
- Split production configuration validation, full/smart context rendering,
  Canvas validation, iOS source checks, natural action dispatch, and importance
  actions into independently testable modules without raising architecture
  budgets.
- Calibrated relative-time and social-scene ranking on source-separated train
  and validation partitions; specific social queries now gate star influence
  by both requested-facet coverage and identity match.
- Preserved the reserved `User` graph anchor during provider-driven type
  correction, and decomposed classification, entity correction, vault import,
  library text shaping, Telegram help, salience evidence projection, and
  store-policy checks into bounded phases.

### Security

- Portable vault projection now excludes every artifact derived solely from a
  private entry, including entity attributes, aliases, relationships, events,
  documents, counts, timestamps, Bases, and Canvas nodes.
- Vector search now applies the authenticated tenant boundary before candidate
  text leaves the derived index; SQL/RLS validation remains the final authority.
- Provider credentials are excluded from account exports and application logs.
- Unverified OAuth email addresses cannot link to an existing local account.
- Entry-processing failures return a stable public error instead of raw internal
  exception text.
- Report, graph, and vault JSON responses no longer expose server filesystem
  paths; unexpected route failures use stable public messages and request IDs.
- Distributed rate limiting now fails closed with a retryable `503` in staging
  and production when Redis is unavailable; process-local fallback remains a
  development-only convenience.
- Public-domain evaluation downloads now stream with a hard byte limit and
  reject redirects outside the approved HTTPS source hosts.
- Standard memory context now excludes private document titles and source
  counts; disclosure mode remains explicit and separately tested.

## [0.2.0] - 2026-07-13

### Added

- Versioned FastAPI backend, JWT session rotation, tenant-scoped data model,
  Alembic migrations, async ingestion, export/deletion, and audit events.
- Responsive React/PWA client, Android and iOS source shells, store-review
  metadata, and Obsidian-compatible vault import/export.
- Typed memory ontology, graph-assisted hybrid retrieval, source provenance,
  salience weighting, and deterministic memory-quality evaluations.
