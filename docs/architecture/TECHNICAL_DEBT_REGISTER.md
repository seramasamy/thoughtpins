# Technical Debt Register

Last reviewed: 2026-08-08

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

**Closed 2026-08-06.** Response mapping moved to `api_errors.py`, which was
the last thing in the file the exit condition did not allow. What remains is
app construction, exception handlers, middleware, dependency wiring, and
in-process metric counters — zero routes, zero schemas. The module is 364
lines, down from 519, and the ratchet is tightened to match rather than left
slack for future growth.

### TD-002: Telegram Compatibility Adapter

`src/thoughtpins/bot/commands.py` retains context assembly, legacy command
handlers, and compatibility glue while newer command families live in focused
modules.

- Risk: transport-specific behavior can diverge from the shared chat engine.
- Containment: new product behavior must land in core modules; Telegram code is
  an adapter; line count cannot increase.
- Exit: extract context packaging and conversation compatibility, then leave
  command registration and thin response formatting.

**Restated 2026-08-06 after auditing the imports rather than the line count.**
The size is a symptom; the actual defect is dependency direction.
`chat/engine.py` — core, serving the web and native clients — imports
`generate_conversation_reply` from `bot/commands.py`, a transport adapter.
Every web chat reply is currently produced by a function that lives in the
Telegram module. That is precisely the risk this item names, and it is already
half-admitted in the code: the function's own docstring says it generates a
reply "for any product surface".

- Evidence, measured rather than estimated: bringing `src/thoughtpins/chat`
  under the dependency rule surfaced **ten** forbidden imports across four
  modules, not the single one first suspected.
  - `chat/actions.py` → `bot.journal_commands`, `bot.natural_commands`,
    `bot.profile_commands`, `bot.style_memory`, `founder.ops`
  - `chat/engine.py` → `bot` (reply generation)
  - `chat/memory_answer.py` → `bot.personality`, `bot.style_memory`
  - `chat/models.py`, `chat/store.py` → `bot.natural_commands`
- Why it survived: the rule already forbade `thoughtpins.bot`, but its `paths`
  list covered `memory`, `ingestion`, `vault`, `llm` and `reports` — not
  `chat`. The engine that serves every surface was the one core package
  nobody was checking.
- Contained as of 2026-08-06: `chat` is now inside the rule and all ten
  imports are declared exceptions carrying this item's number. New violations
  fail the gate — verified by adding one and watching the count rise — and the
  gate rejects an exception that stops matching, so the list cannot rot into
  permission.
- Exit: move personality, writing style, and natural-command routing into
  `thoughtpins.chat` — they are product concepts filed under a transport by
  history, not by design — leave re-exports in `bot/` for the adapter, and
  delete each exception as its import disappears. The conversation cache is
  already correctly placed in `chat/conversation_state.py`, so no state moves.
- Deliberately not attempted in the same pass that found it: the move relocates
  module-level cache state shared by several call sites, and shipping that
  half-done would put every chat reply at risk to close a documentation item.

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

## Closed In The 2026-08-06 Pass

- **Voice retention could be enabled onto a disposable filesystem.** The archive
  writes to a path that a container rebuilds on every deploy, so an operator who
  turned retention on without a mounted volume would take a user's consent to
  keep their recordings and then lose them — discovered only when someone went
  looking for audio that was gone. Startup now refuses that combination, with an
  explicit override for durable storage the check cannot recognise.
- **Editing a chat turn had no implementation.** Now supported end to end. The
  product-specific part is that a retired turn may have written a journal entry:
  it is neither deleted nor silently orphaned, but kept and reported so the
  interface can raise it. Fifteen tests cover ownership, cross-conversation
  isolation, timestamp ties, and double-retirement.
- **Three files crossed their size budgets** while the above landed. Rather than
  granting new ratchets — the policy is that files may shrink, not grow — the
  editor moved to its own component, declarative plumbing moved out of the model
  module, and Telegram startup policy moved out of configuration. All three are
  back under the default budget with no ratchet added.

## Closed In The 2026-08-07 Robustness Pass

- **Near-duplicate answers were never diversified.** `_needs_diversification`
  asked whether the pool held several distinct evidence *views* — multiple
  retrieval channels, repeated source keys, differing social facets. A pool of
  near-identical memories arriving on one channel from different entries
  answered no to all three, so maximal marginal relevance was skipped exactly
  when it was most needed and the answer became the same sentence four times.
  Found by an adversarial test written to fail rather than to reassure. The
  check now also measures textual redundancy across the selectable head.
- **A property test over randomised corpora** surfaced that `rerank_results`
  writes fused scores back onto its inputs, so replaying over the same objects
  compounds one ranking pass on another. That is why
  `clone_candidates_for_rerank` exists; it is now pinned by a named test
  instead of being a footgun documented only in a docstring.

Recorded because it matters more than the fixes: the existing social-relevance
harness reports 1.0 across five thousand randomised cases. A benchmark that
never fails has stopped measuring — it proves only that the generator and the
ranker agree about what is easy. The new suite is built the other way round:
each case is a specific way ranking is known to go wrong, with a distractor
engineered to beat the right answer on some signal the ranker uses.

## Closed In The 2026-08-08 Surface Pass

Two surfaces had been asserted production-grade without being re-checked since
they were last changed. Both had real faults.

- **The README did not render.** The banner used `<picture>` with relative paths
  in `<source srcset>`; GitHub rewrites relative URLs in an `img` src but not
  inside srcset, so both sources failed and — because sources take priority over
  the fallback — nothing displayed at all. The CI badge returned 404 because
  Actions badges do not exist for private repositories, rendering as a broken
  image beside the licence badge. Now a single `img`, a static gates badge, and
  a check that strips HTML comments then verifies every image resolves, every
  remote badge returns 200, every relative link exists, and tables are not
  ragged.
- **The Telegram adapter had two latent crashes**, both the same shape:
  `data.get(k) if isinstance(data.get(k), dict) else {}`. Calling `.get` twice
  asks a reader — and a type checker — to believe two separate lookups agree.
  Now read once and narrowed on the local. Ten files were unformatted and three
  pytest cache directories were sitting in the project root.

Added the contract that actually matters for that surface: Telegram rejects the
entire send on malformed HTML, so a stray unbalanced tag does not degrade a
message, it replaces a good answer with silence. Every message shape the adapter
can emit is now asserted valid against hostile input — script tags, unbalanced
markup, six-thousand-character replies, emoji runs, and bare ampersands — plus a
case proving a trim never cuts an HTML entity in half. The adapter went from 31
tests to 54.

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
