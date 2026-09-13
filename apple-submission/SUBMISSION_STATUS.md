# Submission status — Thought Pins 1.0.0

Updated 13 September 2026. Read this with the
[stability changes](../docs/release/RELEASE_STABILITY_20260913.md) and the
[App Store preparation log](../docs/release/APP_STORE_PREPARATION.md).
Evidence belongs to the linked commit and build; it does not automatically
transfer to a later deployment or a signed distribution archive.

Apple has requested additional information under Guideline 2.1 for the new
submission. The [six-part response and physical-device walkthrough](GUIDELINE_2_1_RESPONSE.md)
must be completed for the chosen signed build and included in both the reply
and App Review Notes. The physical-device recording, current demo credentials,
and console metadata have not been verified by the automated source checks.
The [Apple sign-in guide](APPLE_SIGN_IN.md) distinguishes native and web setup,
Sign in with Apple keys and App Store Connect keys, and real authorization from
mock-provider coverage. These remain submission work, not inferred passes.

## Verified code revision

Backend revision `3ac5e61` passes the Python, PostgreSQL, browser, container and
Android jobs in [run 34736242631](https://github.com/seramasamy/thoughtpins/actions/runs/34736242631)
and the [strict release rehearsal](https://github.com/seramasamy/thoughtpins/actions/runs/34736243383).
It changes hosted ingestion storage only; native and frontend source are
unchanged from `c3eb4cf`, which passes every job, including both native device
families and the archive, in
[run 34735541506](https://github.com/seramasamy/thoughtpins/actions/runs/34735541506).
The later backend run explicitly omits native jobs. This status update changes
documentation only. Browser reports, native screenshots, the unsigned archive,
CI logs and source bundles have private recovery copies.

| Evidence | Result and scope |
| --- | --- |
| Native tests | iPhone 17 Pro and iPad Pro 13-inch (M5), iOS 26.5: eight model and six UI tests each, no failures or skips. Includes complete signup, password editing and recovery, navigation, capture failure recovery and largest Dynamic Type; iPad also exercises landscape. |
| Shared Swift package | 88 tests pass in CI and on the local iOS 17.2 simulator. |
| Production archive | Unsigned arm64 archive, version 1.0.0 / build 298, Xcode 26.6 / iOS 26.5 SDK; built bundle checks pass. Distribution signing and a signed-device pass remain required. |
| Older supported OS | Local iOS 17.2 model/UI review passes all 14 tests; the final keyboard-dismissal correction passes both focused authentication tests. Earlier iPhone SE and dark-mode iPad evidence remains historical. |
| Repository release gate | All 48 top-level strict checks pass, including two proof-artifact self-checks; 923 Python tests pass with 16 optional Telegram skips; 470 files pass typing. PostgreSQL CI passes 920 tests with 19 environment-specific skips. |
| Browser workflows | 379 app, website, PWA and browser-engine cases pass in CI. The hosted web app passes 69 checks at phone, tablet and desktop widths, including 15 axe audits, login, navigation, preferences, refresh, export and logout. In-app account deletion also passes against the live API. |
| Hosted data lifecycle | Four fictional accounts cover same-name originals, owner isolation, PDF/image/text extraction, asynchronous processing, chat edit/recall, resumable preview/apply and export. After deletion, all 28 account-scoped SQL tables have zero matching rows, vector counts are zero and account tombstones have cleared identifying fields. A final export/deletion check confirms no remaining API or worker vault projection. |

Native XCTest sources now live in
[`mobile/ios/ThoughtPinsUIReview/`](../mobile/ios/ThoughtPinsUIReview/README.md)
and use fictional loopback fixtures without production credentials or paid
model calls. Both device families must pass before CI creates the archive.

## Hosted deployment

The API and worker run the archived source of `3ac5e61`; eight affected module
hashes match on each running service. Both Railway deployments report success.
The hosted web app was tested through `https://thoughtpins.com/app/`; its
frontend source is unchanged by the later storage-only revision.

Migration `0027_vault_import_chunks` is applied. Both new storage tables have
enabled and forced PostgreSQL row-level security and application-role grants.
The remote vector collection has its required `user_id` keyword index; actual
tenant-filtered queries pass with strict filtering enabled. Synthetic vector
fixtures and all four temporary accounts were removed after verification.

Uploaded originals and resumable chunks use encrypted, account-owned shared
storage. Hosted workers no longer regenerate decrypted vault directories;
explicit user-requested exports remain available. See the
[storage operations guide](../docs/operations/SHARED_UPLOAD_STORAGE.md) for
legacy reconciliation, capacity and rollback constraints. A database backup
was taken before migration and its restore catalog checked. That check does
not establish a full restore rehearsal. Recovery material remains private.

## Remaining distribution work

1. **Configure distribution signing.** The reviewed Mac had an Apple
   Development identity but no Apple Distribution identity. The six signing /
   App Store Connect secret names expected by the GitHub workflow were absent.
   Configure a certificate, provisioning, team and App Store Connect access on
   the chosen release host. Do not put signing material in Git.
2. **Build and validate a signed archive of the chosen commit.** GitHub Actions
   already supports this path; Xcode Cloud is optional. Validation and upload
   are separate: `upload_testflight` defaults to false. Follow the
   [signed archive runbook](../docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md).
3. **Verify the standing review account.** Live backend workflows now pass
   with disposable fictional accounts. The standing demo password and its
   content were not reset or verified during this pass. Use a fictional
   account whose credentials are in App Store Connect's Sign-In Information.
   Confirm it has usable content, can get through consent/access controls, and
   remains available during review. Confirm provider limits, backups, recovery
   and monitoring against the actual deployment.
4. **Complete the physical-device pass.** Check signed Keychain persistence,
   enabled identity providers, password managers, microphone denial and
   interruption, offline/reconnect behavior, VoiceOver, and iPad multitasking.
   [Device steps](../docs/release/DEVICE_TEST_SCRIPT.md).
5. **Refresh the submission material.** Capture screenshots from the chosen
   release, check the current App Store Connect display requirements, reconcile
   App Privacy answers with the built manifest and actual provider data flows,
   and review all metadata and URLs. Historical screenshots are not evidence
   of the current UI.
6. **Finish Apple provider setup if it will be offered.** The native and web
   integration has automated coverage, but production Apple sign-in is not
   activated. Verify the supplied key's permitted service and primary App ID,
   capability and provisioning. Web needs its registered Services ID, domain
   and exact return URL. An App Store Connect team API key also needs its Issuer
   ID and cannot substitute for a Sign in with Apple key. Complete real Apple
   account sign-in, Hide My Email and deletion/revocation checks before enabling
   the provider. See the [Apple sign-in guide](APPLE_SIGN_IN.md).

No physical device was connected during this session. Simulator recordings and
the unsigned archive do not satisfy Apple's requested latest-OS physical-device
recording. The six-part response is prepared but has not been sent to App Review
or entered into App Store Connect; complete the build, recording, demo-access
and deployment-specific disclosure fields before submitting it.

Apple requires a complete app, functional URLs, device testing and review
access; account-creating apps must support in-app account deletion.
[App Review guidance](https://developer.apple.com/app-store/review/) ·
[Account deletion guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/).

## Decisions to preserve

- V1 is free: no purchases, subscriptions, external purchase links, or ads.
  `deploy/store/commerce-policy.json` and the free-launch gate own this contract.
- iOS uses the app's own sign-in flow when native providers are unavailable.
  Google is suppressed unless the native configuration can also offer Apple.
  A server-side Google flag alone does not establish native availability.
- Automatic strong-password generation remains deferred until the web-credentials
  association and signed-device behavior are verified. Ordinary AutoFill is enabled.
- The app is universal: iPhone and iPad need their own review evidence.
- Journal content, credentials, account databases and generated review reports
  remain outside Git. The committed fixtures are fictional.

## Historical evidence

Revision `5c1bdbd` passed
[run 34655594573](https://github.com/seramasamy/thoughtpins/actions/runs/34655594573)
with unsigned archive build 277, 87 shared Swift tests and 894 Python tests.
Its earlier deployment/cache observations are superseded by the hosted
verification above; they do not describe the current deployment.

The preceding code revision `c391f87` passed
[run 34648674019](https://github.com/seramasamy/thoughtpins/actions/runs/34648674019),
with archive build 269, 78 shared Swift tests and 215 browser cases. Its source
and review evidence remain in the earlier verified recovery packet; the current
preparation adds session corrections and broader browser coverage.

The previous status narrative is preserved in
[the 29 August status at the earlier revision](https://github.com/seramasamy/thoughtpins/blob/6481ffd039b409bea91fb52219cc7f2d2ac11d4f/apple-submission/SUBMISSION_STATUS.md).
It contains useful earlier findings, but statements that the app has never
compiled, that native tests are uncommitted, or that this Mac cannot run the
release gate are superseded by the evidence above. Earlier live checks must
be repeated before submission; they are not current production attestations.
