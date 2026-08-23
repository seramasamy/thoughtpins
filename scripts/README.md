# Gates And Operational Scripts

113 scripts. Most are gates: they encode a rule that was learned once, usually
from something breaking, so it cannot be un-learned quietly. A check here is
cheaper than the incident that produced it.

Run everything the way CI does:

```bash
python scripts/release_check.py --strict-quality
```

That is the single entry point — 49 steps including the full test suite, roughly
twelve minutes. Do not pipe it through `tail`: the summary is ~49 lines and
truncating it hides the pytest result, which is how a red gate once went
unnoticed for three days.

## What the families do

**`check_*` (31)** — fitness functions that fail the build. Architecture and
dependency direction, tenant isolation coverage, secret and export hygiene,
store submission packets, web contracts, dependency locks. Each one prints the
reason it failed rather than a status code.

**`evaluate_*` and `verify_*` and `smoke_*` (22)** — measurements rather than
gates. Retrieval quality against held-out sets, LLM behaviour matrices,
PostgreSQL RLS against a non-owner role, startup and shutdown, Qdrant snapshot
restore. These need real infrastructure and are not part of the offline gate.

**The rest** — release, export, and generation tooling: `export_vault.py`,
`generate_sbom.py`, `create_public_export.py`, `ios_release.sh`,
`bootstrap_macos.sh`.

## Two rules that exist for a reason

**A gate belongs in both runners.** `release_check.py` and
`.github/workflows/ci.yml` must both run it. Adding a check to the one in front
of you and not the other has happened twice: the optional-extras dependency
audit ran locally while CI audited 78 of 205 packages and reported clean, and
the production configuration shape drifted by twenty-six keys between two
hand-maintained copies. `tests/test_ci_runs_the_security_gates.py` now pins the
security-critical set by name.

**A synthetic environment lives in one place.** `production_smoke_env.py` is the
only definition of a production-shaped configuration, imported by the release
gate and by `check_production_config_shape.py`, which is what the workflow runs.
