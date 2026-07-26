# Obsidian Interoperability

Thought Pins treats an Obsidian vault as a portable projection, not as the live
memory database. SQL remains authoritative for tenant ownership, corrections,
temporal validity, deletion, and ingestion state. Vector and graph indexes are
rebuildable retrieval structures. The vault is the user's readable archive and
must remain useful without Thought Pins, a provider account, or a plugin.

## Design Inputs

The export contract follows Obsidian's published formats and incorporates the
useful format discipline from `kepano/obsidian-skills`:

- <https://github.com/kepano/obsidian-skills>
- <https://obsidian.md/help/properties>
- <https://obsidian.md/help/bases/syntax>
- <https://jsoncanvas.org/spec/1.0/>
- <https://obsidian.md/help/cli>

`obsidian-skills` is an instruction set for coding agents. It is not vendored,
called at runtime, or required to open an export. Thought Pins adopts the open
file-format practices that improve interoperability: typed properties, native
Bases, standard JSON Canvas, explicit link validation, and optional CLI
acceptance checks. Its Defuddle guidance is not a new product dependency;
Thought Pins keeps its existing authorized source-ingestion pipeline.

## Delivery Plan And Acceptance Matrix

The integration is split at format boundaries so Obsidian remains optional and
the memory engine remains testable without a desktop application.

| Phase | Engineering work | Acceptance condition | Status |
| --- | --- | --- | --- |
| 1. Format contract | Parse and render typed YAML properties with bounded safe loading; retain list, date, number, boolean, and nested link semantics. | Round trips preserve property types; malformed or recursive YAML cannot exhaust the importer. | Complete |
| 2. Native views | Generate core Bases for journal entries, daily notes, memory cards, and the source library. | Every Base parses as bounded YAML, references valid properties, and opens without a community plugin. | Complete |
| 3. Memory map | Project public entities and relationships into deterministic JSON Canvas 1.0 nodes and edges. | IDs, geometry, paths, and edge references validate; identical input produces identical output. | Complete |
| 4. Import semantics | Route journal-like Markdown to journal ingestion, ordinary notes and user Canvases to the source library, and ignore structural Bases. | Importing an export cannot amplify generated cards or indexes; user-authored Canvas content remains recallable. | Complete |
| 5. Privacy projection | Build every exported artifact from public provenance rather than filtering rendered files after the fact. | Private-only facts cannot appear in Markdown, Bases, Canvas, names, paths, counts, timestamps, manifest metadata, or ZIP bytes. | Complete |
| 6. Validation | Validate Markdown links, wikilinks, properties, Base definitions, Canvas structure, paths, manifests, and archives. | Invalid structure yields actionable errors; valid v1 and v2 exports remain accepted. | Complete |
| 7. Product contract | Keep API responses and web, iOS, and Android clients aligned with structural-file and Canvas import counters. | Generated OpenAPI and all client models agree; account UI explains what is imported. | Complete |
| 8. Application handoff | Add a read-only probe for an installed Obsidian vault and its official CLI. | Offline probe passes everywhere; CLI probe reads Home, queries Journal Base, checks links/errors, and optionally captures a screenshot. | Complete |
| 9. Durable transfer | Stage checksummed chunks, persist offsets, preview changes, and support cancellation/recovery. | Interrupted uploads resume safely; apply is explicit and tenant scoped. | Complete |
| 10. Incremental projection | Track generated hashes without claiming user-authored files. | User edits survive by default; stale generated files are removed only when unchanged. | Complete |
| 11. Scale envelope | Exercise realistic large vaults with bounded result sets and RSS sampling. | 10,000-note export validates cleanly and 100,000-note preview performs no writes. | Complete |

Changes to this contract follow these gates:

1. Add or update focused exporter, importer, parser, Base, Canvas, and privacy
   tests before changing a generated format.
2. Regenerate OpenAPI and native client models when response counters or import
   semantics change.
3. Run the isolated-vault and live-corpus stress harnesses. Both must report
   zero validator errors and preserve ZIP/YAML/Markdown round trips.
4. Run the full Python suite, static analysis, production frontend build,
   Playwright review, PWA offline test, and three-engine responsive audit.
5. On a release Mac or Windows workstation with a current Obsidian installer,
   run the strict CLI probe against a registered copy of the export. The probe
   is an acceptance test, not a runtime dependency.

## Version 2 Export Contract

Every generated Markdown note has `thoughtpins_schema: 2` plus stable identity,
type, title, timestamps, source, tags, aliases, and related links. Properties
remain ordinary YAML values. Dates are ISO strings, importance is an integer or
null, and list-valued fields remain YAML lists.

The generated layout adds `_Views/`:

- `Journal.base` provides recent and high-importance entry views.
- `Daily Notes.base` exposes daily rollups and entry counts.
- `Memory Cards.base` provides card and table views over people, places,
  organizations, projects, events, things, and concepts.
- `Library.base` organizes user-provided and legally portable reading sources.
- `Memory Map.canvas` is a deterministic JSON Canvas projection of exported
  entities and relationships.

The Base files use core table, cards, and list semantics only. The Canvas uses
standard file, text, and group nodes plus directed edges. No community plugin,
theme, remote font, or executable content is required.

## Privacy And Provenance

Portable export is fail-closed. An entry marked private contributes nothing to
the export, including derived memories, relationships, events, documents,
entity-only cards, aliases, attributes, counts, or timestamps. Entity
attributes are exported only when `source_entry_id` identifies a non-private
entry in the same export. Legacy attributes without provenance are omitted.

This is stricter than filtering raw Markdown alone. It prevents a private fact
from leaking indirectly through a public person's card, the memory Canvas, a
Base result, an index count, or the ZIP manifest. Tests scan every emitted file
and the final ZIP for private-only canaries.

Third-party source text follows the source export policy independently of note
privacy. Where portable reuse is not permitted, the vault keeps the user's
derived memory, title, publisher, and original link without copying source
text.

## Import Boundary

Uploaded ZIPs are checked for traversal, symbolic links, encryption, member
count, expanded size, per-file size, compression ratio, path depth, and UTF-8
validity. YAML properties use `safe_load` behind explicit byte, depth, key,
collection, node, and scalar limits. Recursive aliases are rejected. Invalid
properties degrade to body-only import with a warning rather than aborting an
otherwise valid vault.

Markdown classification preserves the autobiographical boundary: explicit
journal/daily/diary notes enter the journal ingestion queue; other notes enter
the source library. User-authored `.canvas` files are flattened into bounded
library documents so their text nodes, file references, links, and labeled
connections become recallable. `.base` files are query definitions and are
ignored as content. A Thought Pins v2 re-import skips its generated Bases,
Canvas, indexes, rollups, and cards to avoid derived-data amplification.

### Resumable Transfer State Machine

Large imports use a durable session with the states `uploading`, `uploaded`,
`previewing`, `preview_ready`, `applying`, and `completed`, plus terminal
`failed`, `canceled`, and `expired` states. Chunks are sequential and carry a
SHA-256 digest. Replaying an already committed chunk is idempotent; gaps,
digest mismatches, oversize archives, cross-tenant access, and invalid state
transitions fail closed. Preview returns aggregate counts plus at most 200
rows. Applying requires the completed preview and records the selected
`skip` or `append` conflict policy.

The web client persists only the opaque session ID, resumes from the server's
committed offset, and asks for confirmation after preview. Native transports
use the same endpoints and checksums. Production API and workers must mount a
shared private staging volume, or replace the local storage adapter with shared
object storage before replicas process transfers independently. Session
records remain in PostgreSQL and recovery requeues interrupted work.

### Incremental Export Ownership

`_System/thoughtpins-export-state.json` records stable generated identities,
paths, and content hashes. It is an ownership ledger, not an index of every
file in the vault. Custom Markdown and Canvas files are never claimed. During
an incremental export, untouched generated files may be updated, unchanged
stale generated files may be removed, and user-modified generated files are
preserved as conflicts unless overwrite is explicitly requested. Atomic
destination-side replacement prevents a partial projection from corrupting a
working vault. Path hints keep generated filenames stable when titles change.

### Measured Scale Envelope

`scripts/benchmark_vault_scale.py` creates disposable synthetic accounts and
records elapsed time, artifact size, and sampled peak resident memory. The
2026-07-19 Windows run produced these results:

- 10,000-entry export, validation, and ZIP: 10,030 files, 6.70 MiB, 227.479
  seconds, 209.40 MiB peak RSS, zero validation errors or warnings.
- 100,000-note import preview: 21.53 MiB archive, 10.866 seconds, 311.75 MiB
  peak RSS, 200 bounded preview rows, zero writes and zero errors.

These are engineering baselines, not universal latency promises. A vault
worker should have at least 512 MiB memory, with 1 GiB preferred for large
archives, and production monitoring should alert on queue age, retries,
session expiry, RSS, archive rejection rate, and apply duration.

## Validation And Acceptance

`validate_vault()` validates Markdown, Base YAML, Canvas JSON, IDs, geometry,
edge references, file references, wikilinks, path portability, required schema
fields, manifest counts, and secret patterns. Generated Canvas IDs and layout
are deterministic, which makes exports diffable and prevents visual churn.

The platform-neutral proof is:

```powershell
python scripts/export_vault.py --zip --obsidian-defaults
python scripts/validate_vault.py .\vault\<user_id>
python scripts/probe_obsidian_vault.py .\vault\<user_id> --json
```

For Obsidian 1.12.7+ with its command-line interface enabled and the exported
vault registered, run:

```powershell
python scripts/probe_obsidian_vault.py .\vault\<user_id> `
  --cli --require-cli --cli-vault-name "<vault-name>" --json
```

The CLI probe is read-only. It reads the home note, searches the vault, lists
properties, queries the generated Journal Base, checks unresolved links, and
captures developer errors. An optional screenshot path exercises Obsidian's
developer screenshot command. The probe never terminates or restarts Obsidian.

The v2 contract was exercised in Obsidian Desktop 1.12.7 on Windows using an
isolated application profile and synthetic vault. Obsidian loaded 43 files,
rendered the Journal Base and Memory Map Canvas, returned all 11 expected Base
rows with Unicode preserved, reported zero unresolved links, and captured no
developer errors. The CLI proof is reproducible with the command above and is
not required by the deployed service.

## Evolution Rules

1. Additive properties do not require a schema bump.
2. Renaming a path, property, type, or generated view requires a migration or a
   new manifest version.
3. Import remains backward compatible with version 1 Markdown exports.
4. Generated views may summarize only records already admitted by the portable
   privacy and source policies.
5. Obsidian-specific behavior belongs in `vault/`; core memory ranking and
   storage must not depend on Obsidian APIs.
