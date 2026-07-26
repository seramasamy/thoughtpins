# Thought Pins Engineering Guide

This file defines repository-wide rules for humans and coding agents. Read it
with `ARCHITECTURE_MODULES.md`, the nearest feature README, and the tests that
own the behavior being changed.

## Product And Privacy Boundaries

- The product name is **Thought Pins**. Package names, bundle identifiers, and
  handles use `thoughtpins` or `ThoughtPins` according to platform convention.
- Journal content, source documents, credentials, local databases, generated
  vaults, reports, and founder-private state never belong in source control.
- The public product must not depend on the local founder adapter. Public app
  behavior belongs under `src/thoughtpins/`; private integration state belongs
  only under ignored `founder/private/` paths.
- Preserve tenant scoping at every persistence boundary. A repository method
  that reads user data must receive or derive a user identifier and enforce it.
- Do not log raw journal text, source text, access tokens, refresh tokens,
  authorization headers, cookies, or provider credentials.

## Architecture Rules

- Keep API routes and transport adapters thin. Put reusable behavior in the
  owning package described by `ARCHITECTURE_MODULES.md`.
- Core packages (`memory`, `ingestion`, `vault`, `llm`, and `reports`) must not
  import FastAPI route modules or Telegram adapters.
- Keep provider integrations behind existing interfaces. Product code must not
  branch on a vendor name when a capability or adapter boundary can express the
  difference.
- Do not add behavior to a grandfathered large module without extracting at
  least the new behavior into a focused module. The architecture budget is a
  ratchet, not a claim that current file sizes are ideal.
- Database schema changes require an Alembic migration, downgrade reasoning,
  tenant-isolation analysis, and tests.
- User-visible data lifecycle changes require export and deletion coverage.

## Change Discipline

1. Read the owning module and tests before editing.
2. Make the smallest coherent change that preserves public contracts.
3. Add tests at the lowest useful layer and an API/workflow test when the
   boundary changes.
4. Run focused tests while iterating.
5. Run `python scripts/release_check.py --strict-quality` before a release.
6. Run `python scripts/check_public_export.py` before creating a public export.

Do not weaken a release gate to make a change pass. If a gate is wrong, update
the implementation, the gate, and the rationale together.

## Platform Commands

```text
python -m pytest
python -m ruff check src tests scripts alembic
python -m mypy src scripts tests
python scripts/check_architecture_budget.py
python scripts/check_public_export.py
cd frontend && npm ci && npm run build
```

On macOS, use `scripts/bootstrap_macos.sh` for a clean development environment
and `scripts/ios_release.sh` for the signed archive preflight. Signing material
stays in Apple Keychain and the developer portal, never in this repository.

## Review Standard

A review should prioritize correctness, privacy, tenant isolation, migration
safety, failure behavior, accessibility, and operability. Cleverness is not a
quality signal. Prefer explicit contracts, deterministic tests, and evidence a
future maintainer can reproduce.
