# Technical Debt Register

Last reviewed: 2026-08-05

This register is intentionally candid. A production codebase with no technical
debt is not a credible claim. Thought Pins uses tests and architecture fitness
functions to keep known debt bounded while high-risk behavior remains stable.

## Operating Policy

- Each debt item has evidence, a containment mechanism, and an exit condition.
- Large legacy modules are size-ratcheted by
  `scripts/check_architecture_budget.py`; they may shrink but may not grow.
- New source files have lower size limits and core layers cannot import
  transport adapters.
- Refactors are feature-sliced and behavior-preserving. Broad file moves are
  not accepted without contract tests and a rollback path.
- Security, privacy, tenant isolation, data loss, and release correctness take
  precedence over cosmetic structural cleanup.

## Active Items

### TD-001: FastAPI Composition Module

`src/thoughtpins/api.py` still contains schemas, middleware, response mapping,
and legacy routes despite the presence of `api_routes/`.

- Risk: high review cost and accidental coupling between route families.
- Containment: no business logic should be added; new routes belong in a router
  module; line count cannot increase.
- Exit: move schemas into feature-owned schema modules, extract remaining route
  families, and leave only app construction, middleware registration, and
  dependency wiring.

The reviewer pass moved memory-card schemas and projections into
`api_memory_cards.py`, removing roughly 400 physical lines from this adapter.
It also moved account-preference resolution into `api_preferences.py`. The
remaining 519-line adapter is ratcheted at its current size.

### TD-002: Telegram Compatibility Adapter

`src/thoughtpins/bot/commands.py` retains context assembly, legacy command
handlers, and compatibility glue while newer command families live in focused
modules.

- Risk: transport-specific behavior can diverge from the shared chat engine.
- Containment: new product behavior must land in core modules; Telegram code is
  an adapter; line count cannot increase.
- Exit: extract context packaging and conversation compatibility, then leave
  command registration and thin response formatting.

The 2026-07-13 reviewer pass extracted bounded conversation persistence,
degraded-mode replies, context budgeting, and portable-vault projection into
`thoughtpins.chat`. Local cache persistence now uses atomic replacement, and
memory reset no longer imports a Telegram transport module. Compatibility
re-exports remain while downstream scripts migrate. The remaining 542-line
adapter is ratcheted at its reduced size.

### TD-004: Stylesheet Concentration

The authenticated web app and marketing site each have a large global
stylesheet.

- Risk: selector coupling and visual regressions across responsive breakpoints.
- Containment: design tokens and contract tests remain authoritative; existing
  files cannot grow.
- Exit: split tokens/base/layout from feature styles without changing selector
  behavior, then add screenshot baselines for the extracted surfaces.

The stylesheet split is complete across foundations, layout, components,
chat, memory, utilities, and responsive layers. Two intentionally broad visual
layers remain exact-size-ratcheted while browser and screenshot contracts guard
their behavior. This item is controlled and can close after those layers are
feature-sliced without changing the public design contract.

### TD-006: Native Execution Evidence

Windows can validate source shape but cannot execute Xcode, iOS Simulator,
code signing, archive validation, TestFlight upload, VoiceOver, or device tests.

- Risk: source checks can miss platform or entitlement failures.
- Containment: native submission remains explicitly false in
  `deploy/store/native-review-handoff.json`; Mac release automation fails closed
  when signing inputs are absent.
- Exit: complete the signed Mac runbook, retain archive/device evidence outside
  source control, and update the handoff only after those artifacts pass.

## Closed In The 2026-08-05 Retrieval Pass

Four defects found by auditing the retrieval path rather than by a failing
test. Each is now covered by a test asserting the property, not the fix.

- **Non-deterministic candidate identity.** Graph evidence was keyed on
  Python's builtin `hash()` of the fact text, which is salted per interpreter.
  The same fact carried a different identity in the API than in the worker and
  a different one on each run, quietly invalidating the replayable-ablation
  property the ranking module documents. Now a BLAKE2b digest, with a test that
  spawns fresh interpreters to confirm agreement and a second test guarding the
  premise so the rationale can be revisited rather than cargo-culted.
- **Session leak on the failure path.** `memory.search` closed a session it
  owned only on the success path, so any raising channel leaked the connection
  under exactly the load that matters. Ownership is now a context manager.
- **Failure isolation applied to one channel of eight.** Only vector retrieval
  was guarded; every other provider could fail the whole query. Each channel is
  now individually absorbed, and fewer candidates is the worst case.
- **Unbounded resolution memo in a long-lived worker.** The entity-resolution
  cache keyed on a hash of the passage — correct, since "Apple" resolves
  differently per context, but it makes keys effectively unique per entry, so
  the dict grew for the life of the process and never released. Now LRU-bounded
  at 4,096 entries, with concurrent-writer coverage. Worker memory is the
  dominant line in this deployment's hosting cost, so the bound is
  load-bearing rather than defensive.

- **Retry without backoff or jitter.** The LLM client paused a constant
  interval between attempts. Against a provider returning 429 that is the wrong
  shape twice: the delay never widens, and every concurrent worker returns to
  the wire at the same instant, so one rate-limit event reconverges into the
  next. Now exponential with full jitter, capped at 8s so a doubling delay
  cannot become a multi-minute stall. Tested for bounds, for growth, and for
  the herd actually spreading across the window rather than clustering.

Structural result: `memory/search.py::search` fell from cyclomatic complexity
30 to 3 by separating orchestration from the eight channel collectors, and the
nineteen ranking coefficients are now declared and bounded in one validated
dataclass instead of a third of them sitting as literals inside the scorer.

Checked and found already correct, recorded so the next audit can skip them:
outbound HTTP carries explicit timeouts; there are no mutable default
arguments anywhere in the tree; vector retrieval enforces tenancy twice, at the
index and again when the hit is re-read through the tenant-scoped SQL query.
The remaining unbounded module state is confined to the founder Telegram
adapter, where an approved-user allowlist bounds it in practice.

## Closed Or Controlled Items

- Native UI is feature-sliced: SwiftUI separates the review shell, screens,
  model, providers, and brand components; Compose separates app composition,
  authentication/consent, navigation, feature screens, account, state, theme,
  reusable components, and the view model. Both consume dedicated core clients.
- Static analysis explicitly targets every production and operational Python
  module, checks typed and untyped function bodies, and reports unreachable
  code, redundant casts, implicit optionals, strict-equality issues, and stale
  suppressions. Third-party implementation internals are skipped. Ruff enforces
  canonical formatting, all Pyflakes findings, import order, and bugbear
  correctness rules across the public tree in both CI and the local release gate.
- The Python maintainability gate scans every production and release function,
  rejects cyclomatic complexity above 30 without legacy exceptions, validates
  UTF-8 source, and runs a high-confidence dead-code check. The current full
  scan covers 2,365 functions with mean complexity below 4.7.
- `uv.lock` resolves every optional Python dependency graph;
  `requirements-prod.lock` is a hash-locked worker/runtime projection consumed
  by the non-root container. A release gate proves both artifacts are current.
- Apache-2.0 is declared in the package metadata and standard project license.
  The owner must still confirm that legal choice before publication.
- Runtime secrets and local data are ignored and scanned out of public exports.
- Local Qdrant remains a founder/development convenience only. Production
  validation requires an authenticated shared Qdrant service and live probe;
  API and worker containers no longer contend over a shared SQLite-backed
  vector directory. Account deletion also fails closed if point deletion
  cannot be confirmed.
- Founder-only integration state is isolated from public product code.
- Database changes are versioned through Alembic.
- PostgreSQL tenant isolation has both application scoping and RLS verification
  paths using a non-owner application role.
- Refresh sessions use atomic compare-and-set consumption, with a forced-race
  test proving that simultaneous rotation has exactly one winner.
- Derived vector candidates are tenant-filtered before retrieval and deletion
  is implemented for every supported local backend. External graph adapters
  remain evaluation-only because their tenant deletion contract is not yet
  verified; production validation rejects their promotion.
- Sanitized exports use an allowlisted tree and exclude runtime state, secrets,
  private founder state, and generated package metadata such as `*.egg-info`.
- Account export/deletion, request IDs, error envelopes, rate limiting, async
  work, health checks, and maintenance behavior have release-gate coverage.

## Review Cadence

Review this register before each minor release and after any security incident,
data migration, store rejection, or major feature slice. Closing an item
requires executable evidence, not only a documentation update.
