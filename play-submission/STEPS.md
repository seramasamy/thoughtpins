# Google Play — exact steps

Literal. Values are copy-paste. Do these in order; steps 1–3 are the ones that
start the clock, so do them first even if you cannot finish the rest today.

**Your identifiers**

| | |
|---|---|
| Package name | `com.thoughtpins.app` |
| App name | `Thought Pins` |
| versionCode | `1` |
| versionName | `1.0.0` |
| minSdk / targetSdk | 26 / 37 |

---

## 1. Register the developer account — $25, one time

play.google.com/console → Get started → **Create a personal account**.

- Google account with 2-Step Verification on.
- Identity verification: government photo ID, plus an address check. Usually
  same-day, sometimes 48 hours.
- $25 once, not annual.

*Done when:* the Play Console dashboard loads and you can select "Create app".

**Know this before you plan anything:** a personal account created recently must
run a **closed test with a minimum number of opted-in testers for 14 consecutive
days** before you may apply for production access. The threshold has changed
twice (it was 20, then reduced) — **read the exact number Play Console shows
you**, and recruit comfortably more than it, because the count is of testers who
actually opt in.

---

## 2. Create the upload keystore — and never lose it

Play binds the app to this key. Lose it and you cannot ship an update, ever.

```bash
keytool -genkeypair -v \
  -keystore thoughtpins-upload.jks \
  -alias upload -keyalg RSA -keysize 4096 -validity 10000
```

On Windows keytool lives at `C:\Program Files\Java\jdk-17\bin\keytool.exe`.

Put the `.jks` and both passwords in your password manager **now**, before you
do anything else with it.

Then create `mobile/android/thoughtpins-app/keystore.properties`:

```properties
storeFile=C:/secure/thoughtpins-upload.jks
storePassword=<store password>
keyAlias=upload
keyPassword=<key password>
```

That file and `*.jks` are gitignored. Verify before committing anything:

```bash
git status --short          # keystore.properties must NOT appear
```

**Enrol in Play App Signing** when Play offers it during the first upload.
Google then holds the real signing key and yours becomes only the *upload* key,
which can be reset if you lose it. Without this, a lost key ends the app.

---

## 3. Build the bundle

```bash
cd mobile/android
./gradlew :thoughtpins-app:bundleRelease
```

Output: `thoughtpins-app/build/outputs/bundle/release/thoughtpins-app-release.aab`

Confirm it is signed — the filename has no `-unsigned`, and the build log shows
a `signReleaseBundle` task. Upload the `.aab`, never the `.apk`.

**Every subsequent upload needs `versionCode` incremented** in
`thoughtpins-app/build.gradle.kts`. Re-using a code is the most common upload
rejection.

---

## 4. Create the app and start the closed test

Play Console → **Create app**.

- App name: `Thought Pins`
- Default language: English (United Kingdom) or (United States)
- App or game: **App**
- Free or paid: **Free** (cannot be changed to paid later)
- Declarations: tick both.

Then **Testing → Closed testing → Create track**:

1. Upload the `.aab`.
2. Add testers by email list or Google Group.
3. Copy the opt-in URL and send it out. **Start today** — the 14 days only count
   while testers are opted in, and removing one restarts the clock.

---

## 5. Store listing and policy forms

These overlap heavily with App Store Connect; answers are pre-derived in
`deploy/store/data-safety-inventory.json`.

**App content → Data safety**
- Collected: email, phone, user ID, user content (journal text), audio, device ID
- Shared with third parties: **No**
- Used for tracking or advertising: **No**
- Encrypted in transit: **Yes**
- Users can request deletion: **Yes** — `https://thoughtpins.com/account/delete`

**App content → other declarations**
- Privacy policy: `https://thoughtpins.com/privacy`
- Ads: **No ads**
- Content rating: complete the IARC questionnaire honestly. User-generated and
  AI-generated text; expect Teen / PEGI 12.
- Target audience: **13+**. Declaring a child audience triggers Families policy,
  which this app is not built for.
- **AI-generated content**: Play has a specific policy for this. Declare it and
  point at `https://thoughtpins.com/ai-disclosure`. Do not skip it.
- Government apps, financial features, health: **No** to all.

**Main store listing**
- Short description (80 chars max): *A private place to keep what matters.*
- Full description: what it does, in plain words. No keyword stuffing — Play
  rejects for it.
- App icon: 512 × 512 PNG
- Feature graphic: 1024 × 500
- Phone screenshots: at least 2, 16:9 or 9:16, 320–3840px. Emulator captures at
  1080 × 2280 qualify.

**One thing worth saying in the listing:** nothing a user writes is ever shared.
No feed, no profiles, no other account can see it. That is what separates this
from the user-generated-content category reviewers scrutinise hardest.

---

## 6. After the 14 days

Play Console → **Production → Apply for production access**. Google reviews the
*application*, separately from reviewing the app. Then promote the build.

---

## Order of operations

Steps 1–4 are the schedule. Everything in step 5 can be done while the closed
test runs. Do not wait until the listing is perfect to start the test.
