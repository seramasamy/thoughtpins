# Client Contracts

`openapi/thoughtpins-v1.openapi.json` is the canonical HTTP contract. CI regenerates
the schema from FastAPI and fails on unreviewed drift. Update it only with an
intentional API change:

```powershell
python scripts/export_openapi.py --update
python scripts/export_openapi.py --check
```

`fixtures/` contains provider-neutral payloads shared by backend, web, iOS, and
Android contract checks. Fixtures contain fictional data only and must never be
generated from a user database.

Authenticated mutations accept `Idempotency-Key`. First-party clients generate
one key per logical operation and retain draft IDs across offline retries.
Collection endpoints retain page-number compatibility and also return a signed
`next_cursor` for stable keyset pagination.
