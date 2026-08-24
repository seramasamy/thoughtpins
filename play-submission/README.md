# Google Play Submission

**Doing it now? → [`STEPS.md`](STEPS.md)** — literal, copy-paste, in order.

**Recommendation: start Play now, in parallel — not instead of Apple.**

Not because Play is faster to launch. It probably is not. Because Play is the
one you can *start today*, and the part that takes longest is a waiting period
that runs on its own once begun.

---

## The honest comparison

| | Google Play | App Store |
|---|---|---|
| Cost | **$25 once** | $99/year |
| Can you start today? | **Yes** — the signed AAB builds on your Windows machine | **No** — needs a Mac you do not have |
| Build verified? | **Yes** — R8 release build installed and run on an emulator, reaching production | Never compiled |
| Longest pole | Closed-test waiting period (see below) | Getting a Mac, then first-build errors |
| Screenshots | Emulator captures are acceptable | Need Xcode simulator |

### The thing that decides the timeline

Google requires **new personal developer accounts** to run a closed test with a
minimum number of opted-in testers for **14 consecutive days** before they may
apply for production access. The threshold was 20 testers at introduction and
has since been reduced — **check the current number in Play Console when you
register**, because it has changed twice and anything written here will age.

**Organisation accounts are exempt**, but registering as an organisation
requires a D-U-N-S number, which itself takes days to obtain.

So the realistic Play path for a solo founder is: register → upload → recruit
testers → **wait 14 days** → apply for production → review. The waiting period
is the schedule.

That is exactly why it is worth starting now. Those 14 days pass while you are
sorting out a Mac. Doing them sequentially wastes a fortnight.

### What Play also buys you

It is a genuine rehearsal. Data safety, content rating, store listing,
screenshots, privacy policy review and account-deletion disclosure are all
required by both stores, and Play's are cheaper to get wrong. Every one of those
artifacts is reusable for App Store Connect.

---

## Readiness: verified, not assumed

Everything below was executed on this machine, not inferred.

| Check | Result |
|---|---|
| `targetSdk` | **37** — Play requires 35+ for new apps |
| `minSdk` | 26 (Android 8.0), ~99% device coverage |
| Release build with R8 + resource shrinking | **builds clean** |
| Release build **runs** | installed on an emulator, launched, rendered, **no crash** |
| kotlinx.serialization survives R8 | yes — the app parsed `/v1/client-config` from production |
| Reaches production API | yes, over `https://api.thoughtpins.com` |
| Signed AAB | **`signReleaseBundle` produced a 4.9 MB signed bundle** |
| Size | 21.8 MB debug → 2.3 MB release APK |
| In-app purchases | none — Play Billing absent, enforced by `check_free_launch.py` |
| Ads / tracking SDKs | none |
| Account deletion in-app | yes, plus the web resource Play now requires |
| Data safety inventory | `deploy/store/data-safety-inventory.json` |

The R8 runtime test mattered. Minification plus `kotlinx.serialization` is the
classic "works in debug, crashes in release" failure, and the only way to know
is to run the minified build. It was run.

---

## Before you upload

### 1. Create the upload keystore — and never lose it

Play binds your app to this key permanently. Losing it means you cannot ship an
update, ever.

```bash
keytool -genkeypair -v \
  -keystore thoughtpins-upload.jks \
  -alias upload -keyalg RSA -keysize 4096 -validity 10000
```

Store the file and both passwords in your password manager. `*.jks`,
`*.keystore` and `keystore.properties` are gitignored — a committed signing key
is unrecoverable.

Then either create `mobile/android/thoughtpins-app/keystore.properties`:

```properties
storeFile=C:/secure/thoughtpins-upload.jks
storePassword=...
keyAlias=upload
keyPassword=...
```

or export `THOUGHTPINS_ANDROID_KEYSTORE`,
`THOUGHTPINS_ANDROID_KEYSTORE_PASSWORD`, `THOUGHTPINS_ANDROID_KEY_ALIAS`,
`THOUGHTPINS_ANDROID_KEY_PASSWORD`. The build registers the signing config only
when all four are present and the file exists, so an unsigned release build
stays possible on a machine without the key.

**Enrol in Play App Signing** when prompted. Google then holds the app signing
key and yours becomes only the upload key, which *can* be reset if lost.

### 2. Build the bundle

```bash
cd mobile/android
./gradlew :thoughtpins-app:bundleRelease
# → thoughtpins-app/build/outputs/bundle/release/thoughtpins-app-release.aab
```

Play takes the `.aab`, not the `.apk`.

### 3. Bump the version for every upload

`versionCode = 1` in `thoughtpins-app/build.gradle.kts`. Play rejects a re-used
code, and this is the single most common upload error.

---

## Play Console setup

Reuse the Apple answers — the questions overlap heavily.

- **Data safety** — from `deploy/store/data-safety-inventory.json`. Collected:
  email, phone, user ID, user content, audio, device ID. All "collected", none
  "shared", **none used for tracking or advertising**. Declare encryption in
  transit and that users can request deletion.
- **Account deletion URL** — `https://thoughtpins.com/account/delete`. Play
  requires this to be reachable *from outside the app*; it is, verified 200.
- **Privacy policy** — `https://thoughtpins.com/privacy`
- **Content rating** — complete the IARC questionnaire honestly. User-generated
  and AI-generated text; expect Teen / PEGI 12.
- **AI-generated content** — Play has a specific policy. Disclose it, and point
  at `https://thoughtpins.com/ai-disclosure`. Do not skip this.
- **Ads** — declare **no ads**.
- **Target audience** — 13+. Declaring a child audience triggers Families
  policy, which this app is not built for.
- **Screenshots** — phone: at least 2, 16:9 or 9:16, 320–3840px. The emulator
  captures at 1080×2280 qualify. Also needs a 512×512 icon and a 1024×500
  feature graphic.

---

## The closed test

1. Create a **Closed testing** track, upload the AAB.
2. Add testers by email list or Google Group. **Recruit more than the minimum** —
   the count is of testers who actually *opt in*, and some never will.
3. They must stay opted in for **14 consecutive days**. Removing a tester
   restarts the clock.
4. Then apply for production access. Google reviews the application itself,
   which is separate from reviewing the app.

Start recruiting on day one. This is the schedule, not the paperwork.

---

## Holes found and fixed in this pass

**No release signing config existed at all.** `buildTypes.release` had
minification and shrinking but no `signingConfig`, so `bundleRelease` produced
an unsigned bundle that Play rejects at upload. Fixed, and verified by building
a genuinely signed AAB against a throwaway key that was then destroyed.

**`.gitignore` did not cover keystores.** No `*.jks`, no `*.keystore`, no
`keystore.properties`. A signing key committed to a repository that is going
public is unrecoverable. Fixed.

---

## Related

- [`../apple-submission/`](../apple-submission/) — the App Store package
- `deploy/store/data-safety-inventory.json` — the answers, in one place
- `deploy/store/commerce-policy.json` — free, no IAP, gate-enforced
