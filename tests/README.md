# Tests

838 tests across 123 files, about seven minutes:

```bash
PYTHONPATH=src python -m pytest tests/ -q
```

`pytest-timeout` is not installed, so `--timeout=` fails with an argument error.
For a change touching one area, run the handful of files that cover it first —
the six chat and Telegram files together take about a hundred seconds — and the
full suite once before committing.

## What is asserted

The suite is written against properties rather than implementations wherever the
property is the thing that matters. A few that are easy to miss:

- **Deletion fails closed.** An account cannot be reported deleted while any
  derived store still holds its data. `test_graph_backend_contracts.py` proves
  this against a backend that refuses, because the real one is not installed —
  the guarantee belongs to the abstraction, so any future driver inherits a
  failing test before its data escapes.
- **Cost shape, not just output.** `test_context_query_cost.py` grows one
  dimension at a time and asserts the query count does not follow. A lazy
  relationship read per row changes nothing a reader can see and everything
  about what the database does.
- **Equivalence at boundaries.** `test_full_context_bounded.py` checks a bounded
  builder against the exact predicate it replaced, on both sides of the limit,
  because the failure is silent: a wrong limit quietly swaps a full journal for
  a sliced one.
- **Thread identity.** `test_telegram_event_loop.py` asserts the model call
  happens off the event loop. The reply is identical either way, so nothing else
  would notice.

## Writing one

Two habits this suite has learned the hard way.

**Verify the test can fail.** Revert the fix and watch it go red. A liveness
test here once passed against the code it was written to reject, because it
sampled after the work finished and a frozen event loop catches up the moment
it is released.

**Drive the real entry point.** A guard called directly proves the guard works,
not that anything calls it. `test_llm_pricing_guard.py` includes a case that
runs `validate_startup()` for exactly this reason — the first version passed
with the check unwired.

Browser tests live in `frontend/e2e/` and run under Playwright with a mocked
API; see `npm run smoke:web`.

`npm run smoke:ios` is the one to know about. It replays nine shipping iPhone
and iPad sizes — including the 320pt iPad Slide Over window, which is narrower
than any iPhone — through **WebKit**, the engine iOS actually runs, and checks
horizontal bleed, 44px touch targets, composer reachability, dark mode and axe
on each. Run it with touch emulation or not at all: the app's 44px minimums live
behind `@media (pointer: coarse)`, so a default desktop context reports every
one of them as a failure that no real device has.
