# Thought Pins Release Versioning

Official store references checked on 2026-07-14:

- Apple App Store Connect version guidance:
  https://developer.apple.com/help/app-store-connect/update-your-app/create-a-new-version
- Apple App Privacy Details:
  https://developer.apple.com/app-store/app-privacy-details/
- Apple App Review Guidelines:
  https://developer.apple.com/app-store/review/guidelines/
- Google Play app bundle and versionCode guidance:
  https://support.google.com/googleplay/android-developer/answer/9859152
- Google Play User Data policy:
  https://support.google.com/googleplay/android-developer/answer/10144311
- Google Play Data safety form guidance:
  https://support.google.com/googleplay/android-developer/answer/10787469

## Version Tracks

- API contract: `/v1`, stable through the first public launch.
- Backend implementation: `API_VERSION`, currently `1.0.0-rc.1` for the local
  release candidate.
- Web app: built from the same repo and served at `/app`.
- iOS app: native `CFBundleShortVersionString` `1.0.0` plus monotonically
  increasing build string, currently `1` in the unsigned source target.
- Android app: native `versionName` `1.0.0` plus monotonically increasing
  `versionCode`, currently `1` in the unsigned source target.

## Rules

- Additive API fields are allowed in `/v1`.
- Removing, renaming, or changing field meaning requires `/v2` or a documented
  deprecation period.
- Every production release must run `python scripts/release_check.py`.
- Every staging/public release must also pass PostgreSQL RLS verification,
  staging smoke tests, load tests, and a backup/restore drill.
- Tag only after the exact release artifact has passed the gate.
- Begin public history with one truthful initial commit. Do not manufacture old
  commits or tags to make a new open-source repository look older.
- Use one monorepo tag for a coordinated release. Store marketing versions and
  build numbers remain independent metadata because Apple and Google require
  their own monotonically increasing build identifiers.

## Native Store Notes

- Apple requires an incremented build string before uploading a new build to App
  Store Connect.
- Google Play requires each uploaded Android App Bundle/APK to use an increased
  `versionCode`, below Play Console's maximum.
- Google Play uses Android App Bundles for distribution; reserve the package
  name carefully because package names are permanent.
- Both stores require privacy disclosures that match actual collection, sharing,
  retention, deletion, LLM provider, OAuth, and crash-reporting behavior.

## Candidate And Public Versions

- Local source/backend/web candidate: `v1.0.0-rc.1`. This identifies the
  coordinated v1 feature set without claiming signed-store or public-service
  proof.
- Coordinated source/backend/web release: `v1.0.0` only after the exact staging
  artifact, signed native builds, and TestFlight/Play internal tests pass.
- iOS: `1.0.0` with build `1`.
- Android: `versionName 1.0.0`, `versionCode 1`.
