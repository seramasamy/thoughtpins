# Thought Pins v1 Mac And Xcode Execution Checklist

Verified against Apple documentation: 2026-07-15

This is the ordered handoff for the first real Mac build. The explanatory
source of truth is
[`MACOS_XCODE_APP_STORE_RUNBOOK.md`](MACOS_XCODE_APP_STORE_RUNBOOK.md). Stop at
the first failed gate; do not compensate by disabling validation or signing
checks.

## 1. Prepare Outside The Repository

- Join the Apple Developer Program and confirm App Store Connect access.
- Register the explicit App ID `com.thoughtpins.app`.
- Enable Sign in with Apple for that App ID.
- Create the App Store Connect app record for **Thought Pins**.
- Create native iOS and server/web Google OAuth clients. Record the iOS client
  ID, server client ID, and reversed iOS callback scheme.
- Prepare `https://thoughtpins.com/privacy`, `/terms`, `/support`,
  `/account/delete`, and `/ai-disclosure` on the production domain.
- Prepare a stable reviewer account with fictional data and store its password
  outside source control.
- Keep the API online for the entire TestFlight and review window.

Apple's current submission page says uploads made on or after April 28, 2026
must use Xcode 26 and the iOS 26 SDK or later. Recheck this before each upload:

- <https://developer.apple.com/app-store/submitting/>
- <https://developer.apple.com/app-store/review/guidelines/>
- <https://developer.apple.com/support/offering-account-deletion-in-your-app>

## 2. Transfer A Clean Source Tree

Transfer a sanitized source export, not the private ZIP containing `.env`.
Before opening it on the Mac, confirm it contains no local database, vault,
logs, reports, backups, user recordings, `.p8`, `.p12`, provisioning profile,
review password, or provider credential.

Keep signing identities in Apple Keychain and release configuration in the
current shell or an encrypted secret manager. A Python virtual environment
cannot emulate macOS, Xcode, Simulator, Keychain, or App Store signing.

## 3. Bootstrap The Mac

Install the current production Xcode, open it once, install an iOS Simulator
runtime, then run:

```bash
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
xcodebuild -version
xcrun simctl list runtimes
brew install python@3.13 node@22 xcodegen
cd /path/to/thoughtpins
chmod +x scripts/bootstrap_macos.sh scripts/prepare_ios_submission.sh scripts/ios_release.sh
./scripts/bootstrap_macos.sh
```

**Go gate:** bootstrap ends successfully, the web production build passes, the
iOS project generates, package resolution succeeds, and an unsigned simulator
build completes.

## 4. Run The Full Source Gate

```bash
source .venv/bin/activate
python scripts/release_check.py --strict-quality
python scripts/check_ios_submission_source.py
python scripts/check_native_review_handoff.py
python scripts/check_store_submission_packet.py
```

**Go gate:** every command exits zero. Archive only the exact source tree that
passed these checks.

## 5. Configure Xcode Signing

1. Open **Xcode > Settings > Accounts** and add the release Apple ID.
2. Let Xcode create or select Apple Development and Apple Distribution
   certificates for the correct team.
3. Generate and open the project:

```bash
cd mobile/ios/ThoughtPinsNative
xcodegen generate
open ThoughtPins.xcodeproj
```

4. Select the Thought Pins target and the correct team.
5. Keep automatic signing enabled for v1.
6. Confirm `com.thoughtpins.app`, the Sign in with Apple capability, the
   privacy manifest, universal iPhone/iPad target, microphone purpose text,
   and full-bleed app icon.

Do not edit the generated project as the source of truth. Put durable project
changes in `project.yml`, regenerate, and rerun the source gates.

## 6. Set Private Release Values

Set these only in the current terminal or secret manager:

```bash
export APPLE_TEAM_ID='ABCDE12345'
export IOS_MARKETING_VERSION='1.0.0'
export IOS_BUILD_NUMBER='1'
export IOS_BUNDLE_ID='com.thoughtpins.app'
export IOS_API_BASE_URL='https://api.thoughtpins.com'
export GOOGLE_IOS_CLIENT_ID='YOUR-IOS-ID.apps.googleusercontent.com'
export GOOGLE_IOS_SERVER_CLIENT_ID='YOUR-SERVER-ID.apps.googleusercontent.com'
export GOOGLE_IOS_REVERSED_CLIENT_ID='com.googleusercontent.apps.YOUR-IOS-ID'
```

The release script accepts all three Google values or none. It rejects partial
configuration and a reversed scheme that does not match the native client ID.
If all three are omitted, the generated release Info.plist removes Google
metadata and the app hides Google sign-in; the production API must advertise
Google OAuth as disabled for that release.

## 7. Test Before Archiving

Run at minimum:

- a large current iPhone, portrait and landscape;
- a standard and compact supported iPhone;
- a 13-inch iPad, both orientations, split view, and Stage Manager;
- a real iPhone near the minimum supported OS;
- a real device on the current iOS release.

Repeat core flows in light/dark mode, default/accessibility Dynamic Type,
VoiceOver, Reduce Motion, poor network, airplane mode, maintenance mode, clean
install, and expired-session state.

Required product flows:

1. Email/phone registration, disclosure consent, login, refresh, and logout.
2. Sign in with Apple for a new and returning account.
3. Google sign-in with a native token accepted by the backend audience.
4. Chat with visible thinking state and a memory-backed answer.
5. Automatic journal routing, correction, undo, and importance rating.
6. Voice recording, denied permission, transcription, and configured audio
   deletion behavior.
7. Allowed link/document import, source detail, search, and provenance.
8. People/place/concept/source cards and daily/weekly/monthly recaps.
9. Offline draft replay exactly once after reconnection.
10. Obsidian vault export and account export.
11. In-app account deletion, token revocation, local session removal, and a
    clean reinstall that does not restore the deleted session.
12. Every privacy, terms, support, AI disclosure, and deletion link.

**Go gate:** no crash, clipped text, blocked dismissal, inaccessible control,
duplicate write, leaked provider detail, stale deleted session, or misleading
success state.

## 8. Build And Verify The Artifact

From the repository root:

```bash
./scripts/ios_release.sh preflight
./scripts/ios_release.sh archive
./scripts/ios_release.sh export
```

The script creates ignored evidence under `reports/ios-release/`, verifies the
signed app with `codesign`, exports an IPA, and writes its SHA-256. It does not
upload automatically.

In Xcode Organizer, validate:

- Thought Pins name, version, build, team, and bundle ID;
- Distribution signature and Sign in with Apple entitlement;
- `PrivacyInfo.xcprivacy` inclusion;
- full-bleed RGB app icon without alpha;
- no debug framework, local path, `.env`, founder adapter, secret, or private
  user artifact in the archive;
- successful **Validate App** result.

## 9. TestFlight And Review

Upload from Organizer only after validation. Use internal TestFlight first,
then a small external group. Repeat the device matrix against the production
API and retain crash, API request-ID, deletion, and legal-link evidence.

In App Store Connect:

- answer App Privacy from actual production data flows;
- complete age rating, encryption, category, support, privacy, and deletion
  metadata;
- disclose AI processing accurately without naming replaceable providers;
- provide the stable reviewer credentials and exact steps to reach chat,
  capture, source library, export, and deletion;
- explain maintenance behavior and any intentionally unavailable feature;
- attach no production key, signing material, or customer data.

Apple requires in-app initiation of account deletion for apps that support
account creation. Sign in with Apple deletion must also revoke the user's
tokens. Recheck:

- <https://developer.apple.com/support/offering-account-deletion-in-your-app>
- <https://developer.apple.com/documentation/technotes/tn3194-handling-account-deletions-and-revoking-tokens-for-sign-in-with-apple>
- <https://developer.apple.com/documentation/bundleresources/privacy-manifest-files>

## 10. Final Go/No-Go Record

Record privately:

- sanitized source archive SHA-256;
- macOS and Xcode versions;
- marketing/build versions and bundle ID;
- Apple team ID, without certificate private material;
- strict-gate output;
- signed archive and IPA SHA-256;
- Organizer validation result;
- tested device/OS/accessibility matrix;
- production API health and legal URL checks;
- TestFlight build number and tester result;
- remaining known limitations and rollback owner.

Do not submit if a required flow is untested, the inference account has no
usable balance, OAuth audiences differ, account deletion is partial, a privacy
answer is uncertain, or the production API cannot stay available through the
review period.
