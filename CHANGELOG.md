# Changelog

All notable changes to Thought Pins are documented here. The format follows
Keep a Changelog, and the project uses semantic versioning for public releases.

## [Unreleased]

### Added

- Scanned PDF pages are read with the local OCR engine. Only pages with almost
  no embedded text that draw a page-sized image are read, so embedded text is
  never replaced. Text extraction, decoding and OCR share a 40-second budget,
  OCR reads at most 20 pages per upload and runs for at most two uploads at
  once (others are told it is busy), and every page not read is reported with
  its reason. Images are found by a bounded, cycle-safe walk of what each page
  draws; JPEG and JPEG 2000 scans are sized from their own headers before
  decoding; OCR output that holds no words is discarded. Pages are read upright
  whether turned by `/Rotate` or by the drawing matrix itself; pages stored as
  strips or tiles are reassembled and read whole, and layered (masked) pages
  that cannot be reassembled are reported as partly read. JBIG2 and JPEG 2000
  decoding runs in a subprocess under the remaining budget as a hard timeout,
  with none of the server's secrets in its environment; pypdf's own JBIG2 path,
  which has none, is never used. A compression filter in front of JBIG2 is
  undone first, and a filter chain hiding a codec is refused. A bilevel page
  decoded with reversed polarity is inverted before OCR, judged on the whole
  page. A malformed `/Rotate` is read as none, as viewers do, and a page that
  cannot be planned fails alone instead of ending the upload. Other encodings
  are decoded at the size the pixel limit checked: an image's soft mask is
  never decoded, LZW and ASCII85 data is read as samples rather than as an
  embedded PNG or TIFF of any size, and CCITT data must be as wide as its
  image. A page drawing more images than the walk takes is reported as partly
  read, and a page whose text cannot be extracted no longer discards the text
  of every other page.
  The image installs `jbig2dec` for JBIG2 scans, and the image build proves
  Tesseract reads generated scanned pages: plain, turned upright by the drawing
  matrix, JPEG 2000, and JBIG2 decoded by the installed `jbig2dec`.
- The Android file picker offers Word and PowerPoint files, matching the web
  app; iOS already accepted any file.

- Word (`.docx`) and PowerPoint (`.pptx`) uploads. Paragraphs, tables,
  footnotes and endnotes are read from Word files; slides are read in
  presentation order with speaker notes and labelled by number. Tracked
  deletions, field codes and duplicate fallback renderings are excluded.
  Parsing uses only the standard library, refuses DTDs at the parser, never
  follows external relationships, and is bounded by entry count, part size,
  total bytes, slide count and text length. Password-protected and legacy
  `.doc`/`.ppt` files are identified as such rather than failing generically.
- Deployment provenance. `/health` reports the commit the API was built from,
  and `/ready` reports the API's and the worker's. The worker publishes its
  revision beside its heartbeat, and Sentry events carry it as the release.
- `scripts/deploy_railway.py`, which deploys one commit from `origin/main` with
  a green `ci.yml` run, refuses when migrations were added since the deployed
  builds, uploads a `git archive` export instead of a working tree, and waits
  until each service reports the new revision. Production had been running
  builds 14 and 18 commits behind `main` with no record of which.

- An independent accuracy audit of the frozen September retrieval backtest,
  with separate metric/statistical code, hand-worked tests, raw-data mapping
  verification and clearer README comparisons against tuned BM25 and prior GLM.
  Reported scores and frozen artifacts are unchanged.

- A public, offline-replayable September retrieval study with numeric features,
  fitted weights, source-ID judgments, predictions, paired statistics and
  experimental ranking tests. The report distinguishes the supported
  model-assisted LongMemEval gain over tuned BM25 from inconclusive local and
  prior-model comparisons. No serving ranker or deployment change.

- The closed-beta invite gate in both native apps: status and redemption in each
  mobile core, a gate screen routed after the consent step, and account deletion
  reachable from behind the gate — an account that cannot use the product yet
  can still leave it.
- Android release signing via a gitignored `keystore.properties` or environment
  variables, registered only when the material is present so an unsigned local
  release build still works. Verified end to end with a signed App Bundle.
- Public pages answer `HEAD` as well as `GET`, so uptime monitors and link
  checkers see the same 200 a browser does instead of a 405.
- A documentation link-integrity gate: every relative Markdown link in the tree
  must resolve, in CI and the release gate.

### Fixed

- A damaged Word or PowerPoint file returned HTTP 500: a corrupt deflate or
  bzip2 stream raised from the decompressor, outside the handled errors. It
  now returns the unreadable-file result asking for pasted text.
- A small, highly compressible Office upload could inflate to 31 MiB of XML
  and cost the API 14 s and 277 MiB. Parts that expand more than 100:1 are
  refused before inflating, and part and package limits are 16 and 48 MiB.
- Production logs recorded entity names drawn from journal entries when an
  entity was created or its type corrected. Those lines now log an identifier
  and type. 41 further log calls printed exception text, which can quote SQL
  parameters, parser input, provider requests or file paths named after notes;
  they now log the exception type. The log-privacy gate fails on content-named
  arguments -- through slices, f-strings, `.format`, concatenation, containers
  and wrappers, including `logger.opt()` chains -- and on printed exceptions,
  except ten reviewed infrastructure messages.
- `logger.exception()` tracebacks ended with the exception's message, which a
  call-site rule cannot see. A Loguru patcher now replaces each logged
  exception with a stand-in of the same type whose message is withheld,
  rebuilt along the cause chain (and through exception groups) with the
  original frames, so every sink -- text, JSON and Sentry's Loguru handler --
  keeps types and frames without text. uvicorn's own traceback for an
  unhandled 500, which Starlette re-raises for the server to log, and Celery's
  task-failure line now pass through the same path: the standard `logging`
  tree is routed into Loguru, uvicorn no longer installs its own handlers, and
  Celery no longer replaces the root logger. From that tree only uvicorn's and
  Celery's INFO lines are kept, and nothing below INFO: httpx logs each
  request's full URL at INFO, which would have put saved article addresses and
  the Telegram bot token in the log, and uvicorn at TRACE logs each request's
  path and query string. Routed lines name the code that logged them, even
  through Sentry's wrapper, and neither the patcher nor the routing ever raises
  into the caller; if a faithful stand-in cannot be built, a generic one is
  logged instead.
- uvicorn's access log recorded every client IP address and each request's
  full path with its query string, including terms typed into library search.
  Access lines now keep method, route and status; a path segment that is not
  identifier-like is shown as `{redacted}`, and so is the name or title given
  to a people, places or library route. A test fails if a route adds a
  free-text path parameter the redaction does not cover.
- Sentry events carried stack-frame local variables and breadcrumbs, both on by
  default in sentry-sdk; on a content route the locals are the journal text.
  Both are now off, and exception messages are withheld before an event is
  sent, leaving the type, stack, route and status. One unhandled 500 reaches
  Sentry three ways -- Starlette, the handler's `logger.exception()` and
  uvicorn's re-log -- and withheld messages defeated Sentry's own
  deduplication, so a report of an exception already sent is now dropped.
- Sentry's own Loguru handlers were added with Loguru's defaults, which render
  local variable values into a logged traceback, and Sentry sent that
  rendering as the event's message: a `logger.exception()` on a content route
  could send what the person wrote. Those handlers are off; Sentry's event
  handler is added like every other sink and sends the log line alone, and a
  log event keeps only its first line. Standard-library messages routed into
  the log keep their first line too: asyncio's report of a failed task quotes
  the exception's text on the next. Those records reach Sentry once, through
  its logging integration, not again through the Loguru handler.
- Uploads held a database connection and the account's row lock while
  extracting text. Extraction now runs first, so OCR and transcription no
  longer block account deletion or hold a pooled connection.
- The Telegram bot ran document and photo extraction on its event loop, which
  a scanned PDF would have frozen for up to 40 s; both now run in a thread, and
  the shared OCR engine is built once under a lock.
- The worker heartbeat used `setex`, which redis-py 8 deprecates and warned
  about on every worker start; it now uses `set(..., ex=)`.
- `scripts/deploy_railway.py` accepted a matching revision beside a failing
  dependency. It now finishes only when `/ready` reports ready with every
  deployed service on the new revision, within `--ready-timeout`, and names
  only the checks the server itself counts as unhealthy.

- Blocking API transactions, authorization, rate limiting, and idempotency
  persistence run outside the event loop. Regression tests hold each boundary
  while an independent health request completes and verify tenant propagation.
- Web uploads report unreadable, partial, queued, and ready results instead of
  equating HTTP success with readable content. PDF extraction reports its
  100-page limit and missing text; photo OCR respects EXIF orientation.
- Voice recording now has playback, explicit save/discard, safe microphone
  cleanup, and an in-memory retry draft with a stable idempotency key.
- Source browsing supports pagination and server-side metadata search beyond
  100 items, with stale response protection. A slow save preserves newly typed
  text, and arriving chat replies do not force a reader away from older turns.

- The chat conversation is one column: the status row, transcript, date
  dividers, empty state, and composer all derive from a single measure instead
  of three that nearly agreed, and the empty state centres itself.
- A daily-ceiling test failed for the forty minutes after midnight UTC because
  it aged records across the boundary; its clock is pinned to midday.

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

- Luminous Memory visual refresh across the public site, the six trust pages,
  the web app and the static fallback. The identity is unchanged (navy night,
  ember brain-pin mark, violet memory accent, native sans); it is rendered as
  light: lit hairlines, glass chrome, ember and violet atmosphere, and a
  memory-network motif. The homepage constellation keeps its 135 motes, pace
  and scroll-to-logo assembly, and adds glowing tones, travelling recall
  signals, a depth layer, a pointer node, floating memory pins and an ignition
  when the mark forms. Trust pages gain a navy dark palette (replacing warm
  brown tokens), reading progress and scrollspy. The app gains a living Chat
  welcome orbit, a night-sky sign-in pane and pointer-lit cards, and fixes
  near-invisible user bubbles in dark mode. Account settings list each
  accepted policy (Privacy Policy, Terms, AI Disclosure) as a link to its
  public page with the accepted version, offering Accept only when a newer
  version applies. New named motions (focus-in,
  signal, orbit, sheen) are documented in `DESIGN.md`; all respect Reduce
  Motion and the homepage pause control, and entrances fade and lift without
  animating blur, which crashed WebKit's software renderer in the browser
  tests. Site cache key `20260925-luminous-3`.
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
