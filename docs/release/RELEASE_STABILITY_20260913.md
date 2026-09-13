# Release stability changes — 13 September 2026

This change addresses the upload, chat, import, extraction and dark-appearance
failures found during hosted verification. It preserves the homepage's floating
memory network and scroll-to-logo animation.

| Surface | Problem and resulting behavior | Verification |
| --- | --- | --- |
| API, worker, all clients | Original uploads used shared timestamp filenames on an ephemeral API disk. Originals now use random account-owned references and encrypted database storage. JSON exports include a manifest; vault ZIPs include the actual bytes. Account deletion removes successful and unreadable originals. | Collision, cross-account export/deletion, wrong-key failure, binary round-trip and cleanup-failure tests; PostgreSQL RLS verifier includes both new tables. |
| Hosted ingestion workers | Automatic vault regeneration could decrypt originals into a second process's filesystem, outside the API's deletion reach. Automatic disk projections now run only in synchronous local mode. User-requested API downloads remain available. | Production and asynchronous processing leave no worker vault; explicit exports retain the original bytes and account deletion removes the shared original and API projection. Synchronous local export still works. |
| Web, iOS, Android chat API | Logical conversation names were looked up as database IDs, and responses could omit the saved user-turn ID. The engine now returns the exact ID and atomically publishes a completed edited branch. Failed edits preserve old history even if an ingestion action committed. Durable journal/source records are retained and their IDs reported. | Actual API edit/resend on three surface names; invalid target, failed processing and retry; existing branch-retirement tests. |
| API and import worker | Preview depended on a staged file existing on both processes. Chunks now live encrypted in shared PostgreSQL and support digest-checked retries across independent filesystem roots. | Separate API/worker paths, preview/apply/cancel, encryption, owner isolation, invalid final digest recovery and refusal to downgrade populated storage. |
| Source library | Model enrichment ran inside the save request. The source and a durable job now commit first; graph extraction and indexing run on the worker. Failed broker dispatch remains retryable. | API proves no inline graph call, source survives unavailable queue, duplicate worker delivery is inert, and another owner cannot enrich the source. |
| Production image | PDF and image parsers were absent. pypdf and Pillow are locked runtime dependencies; Tesseract and English language data are installed. OCR has bounded processing and no first-request model download. | The Docker build extracts a generated PDF and PNG; optional packages merely importing cannot satisfy this check. |
| Native iOS networking | File uploads used the ordinary 30-second request timeout. Uploads now have 120 seconds for transfer and extraction, while ordinary requests retain their existing behavior. | Swift URLSession fixture checks the actual request timeout and background-job response decoding. |
| Web accessibility | Settled success notices and account-deletion text lacked dark-mode contrast. Semantic colors now cover light and dark states; JSON exports are keyboard focusable. Preferences cannot be edited before saved values load. | Full account screens checked with axe at 390, 820 and 1440 CSS pixels in both appearances, plus a delayed-settings response test. |
| Apple sign-in preparation | Web setup inferred the Services ID from audience ordering, and a failed SDK load could prevent retry. The web audience is explicit, native-only configuration hides the web button, and script loading supports preload, timeout and retry. | Generated-key server checks and browser provider fixtures cover success, bad state, incomplete credentials, failed SDK download and native-only gating. Live Apple account authorization still requires portal configuration and a signed-device check. |
| Hosted semantic search | The remote collection lacked a keyword index on `user_id`, so strict filtering rejected scoped queries despite successful vector writes. The adapter now ensures this index exists before reporting readiness, including on newly created collections. | Existing-index preservation, wrong-type rejection, permission failure, initialization checks and live tenant-filtered search/count requests. Strict filtering remains enabled. |
| Native test readiness | The email keyboard satisfied the old letter-key wait while the password input session was still changing. A separate short frame wait raced cold iPad accessibility snapshots. | The shared helper requires the password Go key, usable input bounds and a letter key within the existing twenty-second keyboard deadline. Full-password, editing and login assertions remain required. |

The [storage migration notes](../operations/SHARED_UPLOAD_STORAGE.md) describe
legacy-file reconciliation, encryption, capacity and rollback. Migration 0027
adds only the two storage tables; it refuses destructive rollback while either
contains bytes. The complexity and publication gates remain enforced. The RLS
expectation was extended to require the new tables, and Apple validation now
checks an explicit web audience without requiring a Services ID for native-only
use; a configured web audience still requires its allowlist and return URLs.
The reference scanner permits the configured provider's name only in the two
App Review disclosures that must identify external services. Secret scanning
and founder-reference checks still apply to those files, with a regression
test proving that the exception cannot conceal credentials or private names.

Run `python scripts/release_check.py --strict-quality` and
`python scripts/check_public_export.py` on the candidate. GitHub CI retains
PostgreSQL, browser-engine, native iPhone/iPad and container evidence for the
exact commit. Generated screenshots, hosted test accounts, credentials and
private maintenance reports do not belong in this document or source control.

Apple's Guideline 2.1 response is prepared in the
[six-part review packet](../../apple-submission/GUIDELINE_2_1_RESPONSE.md).
The physical-device recording, signed distribution build, verified review
credentials and App Store Connect reply are distinct from automated checks.
Read the [Apple sign-in guide](../../apple-submission/APPLE_SIGN_IN.md) before
activating the provider. No App Store approval or live Apple login is claimed
from code or mocked authorization tests alone.

The vector index change is additive metadata on the derived remote collection;
it neither rewrites source data nor changes SQL tables. Existing deployments
need permission to create a missing `user_id` keyword payload index. An index
with another type requires explicit repair and fails initialization; the app
does not drop it or disable strict filtering. Keep the compatible index when
rolling back application code. Local Qdrant does not implement payload indexes
and is excluded from this remote requirement.
