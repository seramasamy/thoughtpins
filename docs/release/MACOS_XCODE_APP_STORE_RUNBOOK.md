# macOS, Xcode, Codex, TestFlight, And App Store Runbook

Last reviewed: 2026-07-15

Use [MAC_XCODE_V1_EXECUTION_CHECKLIST.md](MAC_XCODE_V1_EXECUTION_CHECKLIST.md)
as the short, ordered release-day companion to this explanatory runbook.

This is the source-of-truth procedure for turning the reviewable iOS source in
`mobile/ios/` into a signed Thought Pins archive. It covers a clean Mac setup,
Codex, local validation, Apple signing, TestFlight, App Store Connect, review
evidence, and rollback.

## 1. What Can And Cannot Be Virtualized

A Python virtual environment isolates Python packages. It does not provide
macOS, Xcode, iOS Simulator, Apple Keychain, code-signing identities, or App
Store upload tooling.

Use one of these supported release hosts:

1. A physical Mac running a macOS version supported by the current Xcode.
2. A macOS virtual machine running on Apple hardware under Apple's license.
3. A reputable hosted Mac build service, with signing secrets stored in that
   service's encrypted secret store.

Do not treat a macOS image on ordinary Windows hardware as release evidence.
Even if it boots, it is not a dependable or generally compliant App Store
signing path. A Mac mini is the simplest long-lived release host.

Official references:

- [Xcode support and macOS compatibility](https://developer.apple.com/support/xcode/)
- [Preparing an app for distribution](https://developer.apple.com/documentation/xcode/preparing-your-app-for-distribution)
- [Distributing beta tests and releases](https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases)
- [Uploading builds to App Store Connect](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
- [Upcoming App Store submission requirements](https://developer.apple.com/news/upcoming-requirements/)
- [TestFlight](https://developer.apple.com/testflight/)

## 2. Codex On A Mac

Codex runs on macOS. The CLI officially supports macOS and Linux, and the Codex
app is also available on macOS. Use the same repository rules in `AGENTS.md`.

CLI installation:

```bash
npm install -g @openai/codex
codex --login
codex --version
```

Open this repository as the working folder. Keep Codex permissions scoped to
the repository. Do not paste signing private keys, App Store Connect API key
contents, production credentials, or customer data into prompts or committed
files.

Official references:

- [Codex CLI setup](https://help.openai.com/en/articles/11096431)
- [Using Codex with ChatGPT](https://help.openai.com/en/articles/11369540-using-codex-with-chatgpt)
- [Codex CLI sign-in](https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt)

## 3. Required Accounts And Private Values

Before a signed archive, obtain:

- an active Apple Developer Program membership;
- access to the correct App Store Connect team;
- the 10-character Apple Developer Team ID;
- the registered bundle identifier `com.thoughtpins.app`;
- Sign in with Apple enabled for that App ID;
- a unique monotonically increasing build number;
- production and staging HTTPS API endpoints;
- the App Store Connect app record and SKU;
- final privacy answers, age rating, categories, support URL, privacy URL, and
  reviewer account.

Never commit:

- `.p8` App Store Connect API keys;
- `.p12` signing identity exports or passwords;
- `.mobileprovision` profiles;
- Keychain exports;
- review-account passwords;
- production `.env` files;
- OAuth secrets or private service configuration.

Native Google sign-in uses three public build identifiers rather than a client
secret: the iOS client ID, backend/server client ID, and reversed iOS callback
scheme. Keep their release values in the private release environment anyway so
the signed artifact is reproducible and the source defaults stay inert.

Xcode-managed signing stores identities in Keychain and profiles in the user's
Library. That is the preferred initial setup.

## 4. Prepare A Clean Mac

### 4.1 Install Xcode

1. Install the current production Xcode from the Mac App Store or Apple
   Developer downloads. As of this review, App Store Connect requires Xcode 26
   or later with an iOS 26-family SDK; recheck Apple's upcoming-requirements
   page before every release because this floor changes over time.
2. Open Xcode once and allow it to install platform components.
3. In Xcode, open **Settings > Platforms** and install the iOS Simulator runtime
   used for testing.
4. Select the active developer directory and accept the license:

```bash
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
xcodebuild -version
xcrun simctl list runtimes
```

If multiple Xcode versions are installed, record the selected version in the
release evidence. Do not change Xcode versions halfway through a release
candidate without rebuilding all evidence.

### 4.2 Install Command-Line Dependencies

Install Homebrew from its official site if it is not already present, then:

```bash
brew update
brew install python@3.13 node@22 xcodegen
python3.13 --version
node --version
npm --version
xcodegen --version
```

The project supports Python 3.11+, but using the same major version as the
production container reduces drift.

### 4.3 Transfer The Repository Safely

Preferred sequence:

1. Create a sanitized public/source export on the Windows workstation.
2. Verify the export contains no `.env`, database, vault, log, report, backup,
   founder-private state, or credential.
3. Transfer it over an encrypted channel or private removable storage.
4. Create a new local `.env` on the Mac from `.env.example` only if backend work
   is needed.

Do not use the secret-bearing backup ZIP as an open-source or collaborator
transfer artifact.

## 5. Bootstrap The Development Environment

From the repository root:

```bash
chmod +x scripts/bootstrap_macos.sh scripts/prepare_ios_submission.sh scripts/ios_release.sh
./scripts/bootstrap_macos.sh
```

The bootstrap script:

- refuses to run outside macOS;
- verifies Xcode, XcodeGen, Python, Node, and npm;
- creates `.venv`;
- installs Python development dependencies;
- performs a clean `npm ci` and web production build;
- runs iOS source and architecture checks;
- generates `ThoughtPins.xcodeproj` from `project.yml`;
- resolves local Swift packages;
- builds an unsigned generic iOS Simulator target.

Use `./scripts/bootstrap_macos.sh --install-missing` only on a developer-owned
Mac where Homebrew is already installed. The script never installs Xcode and
never changes signing identities.

Manual equivalent:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/check_ios_submission_source.py
python scripts/check_architecture_budget.py
cd mobile/ios/ThoughtPinsNative
xcodegen generate
xcodebuild -resolvePackageDependencies \
  -project ThoughtPins.xcodeproj \
  -scheme ThoughtPins
xcodebuild \
  -project ThoughtPins.xcodeproj \
  -scheme ThoughtPins \
  -configuration Debug \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  clean build
```

Before generating release evidence, return to the repository root with the
virtual environment active and run the complete offline gate:

```bash
python scripts/release_check.py --strict-quality
```

The gate must finish with every local step passed. A missing dependency is a
preflight failure, not a skipped check. Android, PostgreSQL, signed archive,
device, and deployed-service evidence remain separate where the host boundary
requires them.

## 6. Understand The iOS Source Layout

- `mobile/ios/ThoughtPinsNative/project.yml`: reviewable XcodeGen source of
  truth. Do not hand-maintain the generated `.xcodeproj`.
- `mobile/ios/ThoughtPinsNative/Sources/`: app entry point.
- `mobile/ios/ThoughtPinsNative/Resources/`: Info.plist, privacy manifest,
  entitlements, icon, and launch resources.
- `mobile/ios/ThoughtPinsApp/`: SwiftUI application shell.
- `mobile/ios/ThoughtPinsCore/`: API client, models, session, drafts, and
  version policy.

Regenerate after changing `project.yml`:

```bash
cd mobile/ios/ThoughtPinsNative
xcodegen generate
```

Review the generated project diff only as build evidence. The generated
project should not replace `project.yml` as the architectural source.

## 7. Configure Apple Developer Signing

### 7.1 Register The App ID

In Apple Developer **Certificates, Identifiers & Profiles**:

1. Create or verify explicit App ID `com.thoughtpins.app`.
2. Enable **Sign in with Apple**.
3. Do not enable capabilities the shipped binary does not use.
4. If push notifications are deferred, leave the push entitlement out of this
   release rather than requesting an unused capability.

### 7.2 Add The Account In Xcode

1. Open Xcode **Settings > Accounts**.
2. Add the Apple ID associated with the developer team.
3. Select the team and choose **Manage Certificates**.
4. Let Xcode create an Apple Development certificate for device testing.
5. Let Xcode create or use an Apple Distribution certificate for archives.

Back up signing keys only through an approved encrypted process. Never export a
certificate into the repository.

### 7.3 Configure The Target

Generate and open the project:

```bash
cd mobile/ios/ThoughtPinsNative
xcodegen generate
open ThoughtPins.xcodeproj
```

In **ThoughtPins target > Signing & Capabilities**:

1. Select the correct team.
2. Keep **Automatically manage signing** enabled for the first release.
3. Confirm bundle identifier `com.thoughtpins.app`.
4. Confirm **Sign in with Apple** appears once.
5. Resolve all signing status errors before archiving.

Do not commit the team ID into `project.yml`. It is account-specific and is
passed privately to the release script.

## 8. Configure Authentication And Backend Review Access

Before TestFlight:

- Deploy `https://api.thoughtpins.com` with a valid public certificate.
- Keep the API available for the entire review window.
- Configure Apple OAuth audience/client identifiers on the backend.
- Configure the native Sign in with Apple flow and test both a new user and a
  returning user whose email is no longer returned by Apple.
- If Google sign-in is shown, configure and test it. If it is not configured,
  do not show a nonfunctional button.
- Verify email/phone registration, login, refresh rotation, logout, and account
  deletion.
- Create a stable reviewer account containing safe demonstration data.
- Store the reviewer password only in the private release system and App Review
  notes, never in source control.

Run the public URLs from a network not logged into your infrastructure:

```bash
curl --fail --show-error https://thoughtpins.com/privacy
curl --fail --show-error https://thoughtpins.com/terms
curl --fail --show-error https://thoughtpins.com/support
curl --fail --show-error https://thoughtpins.com/account/delete
curl --fail --show-error https://thoughtpins.com/ai-disclosure
curl --fail --show-error https://api.thoughtpins.com/health
```

## 9. Simulator And Device Test Matrix

Use at least:

- current largest iPhone Pro Max, portrait and landscape;
- current standard iPhone, portrait;
- one compact supported iPhone size;
- 13-inch iPad, portrait, landscape, split view, and Stage Manager if
  available;
- one real iPhone running the minimum supported iOS version or the nearest
  practical version;
- one real current-iOS device.

Test with light mode, dark mode, Dynamic Type at default and an accessibility
size, Reduce Motion, VoiceOver, poor network, airplane mode, expired session,
maintenance mode, and a clean install.

Required workflows:

1. Register and accept AI/privacy disclosure.
2. Sign in with Apple.
3. Sign out and sign back in.
4. Send chat; observe thinking state; receive a memory-backed response.
5. Save an unambiguous journal entry and verify classification feedback.
6. Correct an ambiguous route and undo the latest save.
7. Record a voice note only after the microphone prompt; verify the submitted
   public configuration reports that audio was discarded after transcription
   and exposes no voice-archive controls.
8. Deny microphone permission and verify graceful recovery without a recording
   or transcript being created.
9. Pin an allowed link and upload an allowed document.
10. Search and open people/place/source memory cards.
11. View daily, weekly, and monthly recaps.
12. Export account data and an Obsidian-compatible vault.
13. Queue an offline draft, restore connectivity, and verify one-time retry.
14. Trigger maintenance mode and verify clear read-only/retry behavior.
15. Delete the account in app, including confirmation and session removal.
16. Reinstall and verify no deleted session silently returns.
17. Open every legal/support link.

Capture screenshots or a short screen recording for each store-critical flow.
Keep evidence private when it contains the reviewer account or test content.

## 10. Run The Signed Archive Preflight

Set release values only in the current shell or a private secret manager:

```bash
export APPLE_TEAM_ID='ABCDE12345'
export IOS_MARKETING_VERSION='1.0.0'
export IOS_BUILD_NUMBER='1'
export IOS_API_BASE_URL='https://api.thoughtpins.com'
export GOOGLE_IOS_CLIENT_ID='YOUR-IOS-ID.apps.googleusercontent.com'
export GOOGLE_IOS_SERVER_CLIENT_ID='YOUR-SERVER-ID.apps.googleusercontent.com'
export GOOGLE_IOS_REVERSED_CLIENT_ID='com.googleusercontent.apps.YOUR-IOS-ID'
```

Run preflight without signing:

```bash
./scripts/ios_release.sh preflight
```

Create a signed archive:

```bash
./scripts/ios_release.sh archive
```

Create a local App Store distribution export after archive succeeds:

```bash
./scripts/ios_release.sh export
```

The script intentionally does not upload by default. Google sign-in is an
all-or-none release capability: when configured, the script validates that the
reversed callback scheme matches the iOS client ID; when omitted, it removes
the dormant Google keys and empty callback scheme from the built Info.plist.
It also fails if the team ID, versions, HTTPS API URL, tools, source gates,
archive, signature verification, or export fails.
Generated output goes under ignored `build/ios-release/` and evidence under
ignored `reports/ios-release/`.

Build numbers must increase for every App Store Connect upload, including a
replacement for a rejected binary. Marketing version changes only when a new
App Store version is created.

## 11. Inspect The Archive In Xcode Organizer

Open **Window > Organizer > Archives** and select the archive. Confirm:

- app name is Thought Pins;
- bundle identifier is `com.thoughtpins.app`;
- marketing version and build number are correct;
- distribution team is correct;
- app icon is full-bleed and has no alpha channel;
- archive contains `PrivacyInfo.xcprivacy`;
- Sign in with Apple entitlement is present;
- no debug framework, private configuration, founder adapter, local path, or
  credential is bundled;
- release API URL uses HTTPS;
- Xcode validation reports no blocking issue.

Use **Distribute App > App Store Connect > Upload**. Keep Xcode's generated
distribution logs with the private release evidence.

## 12. TestFlight

After App Store Connect finishes processing:

1. Review export-compliance questions. The current source declares no non-exempt
   encryption; confirm this remains accurate for the shipped binary.
2. Add internal testers first.
3. Install from TestFlight on a clean real device.
4. Repeat the store-critical workflow matrix against production review
   infrastructure.
5. Inspect crashes, backend request IDs, job failures, and account deletion.
6. Add external testers only after internal evidence is clean.
7. Provide beta review information if external TestFlight review is required.

Do not use a local or VPN-only backend for review. Reviewers must be able to
reach every core workflow without contacting you for setup.

## 13. App Store Connect Metadata

Complete and cross-check:

- app name, subtitle, description, keywords, category, copyright;
- support, marketing, and privacy-policy URLs;
- age rating questionnaire;
- App Privacy answers matching the privacy manifest and runtime;
- screenshots captured from the native app at required device sizes;
- review contact and stable demo credentials;
- review notes explaining AI processing, account deletion, voice permission,
  maintenance behavior, and any non-obvious demo flow;
- version release behavior (manual release is safer for the first version).

Do not claim on-device-only processing, no third-party processing, or features
that the submitted binary does not provide. Do not mention internal provider
brands when the user-facing product is provider-neutral.

Use `deploy/store/review-notes-template.md` as the starting point and verify it
against the exact binary, backend, and App Store Connect answers.

## 14. Submission Gate

All of the following must be true:

- [ ] Offline release gate passes with strict quality.
- [ ] Public-export and secret scans pass.
- [ ] PostgreSQL migrations and RLS pass in staging with a non-owner role.
- [ ] Signed Xcode archive validates.
- [ ] Clean-device TestFlight matrix passes.
- [ ] Production backend and legal pages are public and monitored.
- [ ] Reviewer account works without privileged/local access.
- [ ] Sign in with Apple works when any third-party login is offered.
- [ ] Account deletion works in app.
- [ ] App Privacy answers match runtime and `PrivacyInfo.xcprivacy`.
- [ ] Screenshots show the submitted native binary.
- [ ] No placeholder URLs, store IDs, demo passwords, or unsupported claims
  remain.
- [ ] `deploy/store/native-review-handoff.json` is updated from false only when
  signed/device evidence actually exists.

Source checks on Windows do not satisfy the signed archive or device gates.

## 15. Rejection And Rollback

If Apple rejects the submission:

1. Preserve the exact rejection text and affected build number.
2. Map the issue to a specific guideline and executable reproduction.
3. Do not argue around a genuine functional or metadata mismatch.
4. Fix code, backend, metadata, or review notes at the owning layer.
5. Add a regression check when the problem is automatable.
6. Increment `IOS_BUILD_NUMBER` and create a new archive.
7. Repeat validation and TestFlight smoke testing.

If a production backend issue appears during review, prefer maintenance mode
with a truthful user-facing message over an unavailable or partially broken
workflow. Restore service, repeat reviewer-account smoke tests, and tell App
Review only when the issue materially affected access.

## 16. Troubleshooting

### Xcode cannot find a profile

- Confirm the bundle ID and selected team.
- Confirm Sign in with Apple is enabled for the App ID.
- Refresh Xcode accounts and profiles.
- Remove stale derived data, regenerate the project, and retry.
- Do not download random profiles or commit one as a workaround.

### Archive menu is disabled

Select **Any iOS Device (arm64)** or a connected device, not a simulator, then
use the Release scheme.

### Package resolution fails

The Swift packages are local. Verify the repository directory structure is
unchanged, regenerate with XcodeGen, then use **File > Packages > Reset Package
Caches** only if necessary.

### App cannot reach the API

- Confirm the release build points to `https://api.thoughtpins.com`.
- Confirm TLS trust from the physical device.
- Check maintenance and minimum-version responses.
- Use backend request IDs; never log or transmit access tokens while debugging.

### Sign in with Apple returns no email

Apple normally returns name/email only on first authorization. The backend must
resolve returning users from the stable Apple subject identifier. Test revoke
and first-login behavior with a dedicated test account.

### Upload succeeds but build is missing

Processing can take time. Check App Store Connect email and processing status
for entitlement, icon, privacy, or binary errors before uploading another build.

## 17. Private Release Evidence Layout

Keep this outside the public repository or under ignored `reports/`:

```text
reports/ios-release/<version>-<build>/
  release-evidence.json
  xcode-version.txt
  archive-validation.log
  distribution-log/
  testflight-smoke.md
  device-matrix.md
  accessibility-results.md
  screenshots/
```

Record the sanitized source commit/hash, Xcode version, macOS version, team ID
(not keys), bundle ID, version/build, backend release identifier, test devices,
gate output, archive timestamp, and App Store Connect processing result.

## 18. Definition Of Done

The iOS app is submission-ready only when a reproducible source revision has a
validated signed archive, a clean TestFlight device run, matching privacy/store
metadata, a reachable review backend, and a working reviewer account. The
current repository can prepare and enforce that process; only a Mac with the
owner's Apple credentials can produce the final signed evidence.
