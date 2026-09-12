# Gates And Operational Scripts

This directory contains release gates, evaluation tools and operational
commands. Gates encode repository contracts and regression checks.

Run everything the way CI does:

```bash
python scripts/release_check.py --strict-quality
```

The runner prints each check and a final summary, including the full test suite.
Retain the complete output and check its exit status; the number of steps and
runtime change with the enabled checks and environment.

## What the families do

**`check_*`** — fitness functions that fail the build. Architecture and
dependency direction, tenant isolation coverage, secret and export hygiene,
store submission packets, web contracts, dependency locks. Each one prints the
reason it failed rather than a status code.

**`evaluate_*`, `verify_*` and `smoke_*`** — retrieval measurements, model
behavior checks, PostgreSQL RLS verification, startup/shutdown and recovery
tests. Some run offline; others require configured infrastructure. Check the
command's options and the release runner before using a production target.

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
