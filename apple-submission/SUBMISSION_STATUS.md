# Submission status — Thought Pins 1.0.0

Updated 13 September 2026. Read this with the
[release review](../docs/release/RELEASE_POLISH_CHANGELOG.md) and the
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

The source at `5c1bdbd` passes all nine jobs in
[GitHub run 34655594573](https://github.com/seramasamy/thoughtpins/actions/runs/34655594573).
This status update changes documentation only. The linked run retains the
browser report, native tests/screenshots and archive; private copies have also
been downloaded for recovery.

| Evidence | Result and scope |
| --- | --- |
| Native tests | iPhone 17 Pro and iPad Pro 13-inch (M5), iOS 26.5: seven model and five UI tests each, no failures or skips. |
| Shared Swift package | 87 tests pass in CI and on the local iOS 17.2 simulator. |
| Production archive | Unsigned arm64 archive, version 1.0.0 / build 277, Xcode 26.6 / iOS 26.5 SDK; built bundle checks pass. This is not an App Store export. |
| Older supported OS | The earlier iOS 17.2 review includes iPhone SE and dark-mode iPad, keyboard/password editing, complete signup, navigation, capture recovery and the largest Dynamic Type accessibility size. Current session changes pass the shared package tests on iOS 17.2. |
| Repository release gate | All 48 top-level strict checks pass, including two proof-artifact self-checks; 894 Python tests pass with 16 optional Telegram skips; 453 files pass typing. |
| Browser workflows | 289 app, website, PWA, WebKit and Firefox cases plus 11 direct session tests pass in CI. A built web app also passes real local-backend login, renewal, export, tenant-isolation and account-deletion checks. |

Native XCTest sources now live in
[`mobile/ios/ThoughtPinsUIReview/`](../mobile/ios/ThoughtPinsUIReview/README.md)
and use fictional loopback fixtures without production credentials or paid
model calls. Both device families must pass before CI creates the archive.

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
3. **Verify the production backend and review account.** Use a fictional
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
6. **Deploy the intended web/backend revision.** A GitHub push does not prove
   thoughtpins.com runs that revision. The preparation check still returned
   older website/app cache keys. Record the deployed
   revision before calling the hosted experience verified.

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
