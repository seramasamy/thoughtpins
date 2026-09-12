# Contributing To Thought Pins

Thought Pins is a memory and journaling system. Contributions should preserve
tenant isolation, data lifecycle behavior and the existing release gates.

## Development Setup

Requirements:

- Python 3.13 for the pinned development environment; see `pyproject.toml` for supported versions
- Node.js 22
- PostgreSQL 16 and Redis 7 for production-parity integration tests
- Current Xcode on macOS for iOS work
- JDK 17 and the checked-in Gradle wrapper for Android work

```text
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install uv==0.11.28
python -m uv sync --frozen --extra dev
cd frontend
npm ci
cd ..
```

Copy `.env.example` to `.env` for local development. Never commit `.env`, real
tokens, production URLs containing credentials, user journals, databases,
exports, screenshots containing private data, or signing files.

`uv.lock` is the complete dependency resolution. `requirements-prod.lock` is
the hash-locked production projection used by Docker. Dependency changes must
update both and pass `python scripts/check_dependency_locks.py`.

## Repository Layout

Use `ARCHITECTURE_MODULES.md` as the ownership map and `AGENTS.md` as the
repository engineering contract. New business behavior belongs in a focused
feature module; API, web, native, and Telegram surfaces adapt that behavior.

The known large modules are tracked in
`docs/architecture/TECHNICAL_DEBT_REGISTER.md`. The architecture budget prevents
them from growing and applies stricter limits to new modules.

## Verification

Run focused tests first, then the offline release gate:

```text
python -m pytest tests/path_to_changed_area.py
python scripts/release_check.py --strict-quality
```

Frontend changes also require:

```text
cd frontend
npm run build
npx playwright install chromium
npm run smoke:web
```

Database and tenant-isolation changes require PostgreSQL, migrations from an
empty database, and `python scripts/verify_postgres_rls.py` using a non-owner
application role. SQLite tests do not prove PostgreSQL row-level security.

iOS changes must pass the Mac workflow in
`docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md`. Android changes must pass
`./gradlew test assembleDebug` and a device or emulator smoke test when they
affect UI or platform integration.

## Pull Request Expectations

- State the user-visible behavior and failure behavior.
- Link tests to each changed contract.
- Document migrations, compatibility, rollout, and rollback when applicable.
- Include accessibility evidence for UI changes.
- Update privacy and store metadata when data collection or third-party
  processing changes.
- Keep generated output and private evidence out of commits.
- Run `python scripts/check_public_export.py` before requesting public review.

## Security Reports

Do not file public issues for vulnerabilities or suspected data exposure. Use
the repository host's private vulnerability reporting channel described in
`SECURITY.md`.
