# Submission status — Thought Pins 1.0.0

**Last updated:** 2026-08-29, after the pre-submission audit run.
**Written for:** someone on a Windows machine, with no Mac and no memory of how
any of this happened.

Single source of truth. If this file and anything else disagree, this file is
newer.

---

## Read this first

**One thing must be done on a Mac, and it may already be too late.**

Xcode Cloud's first setup can only be started from Xcode. Apple's own words:
*"Use Xcode to initially configure your project or workspace to use Xcode Cloud.
After you complete your first build, use either Xcode or App Store Connect."*
The App Store Connect API cannot create the product either — `ciProducts` is
read and delete only.

Everything the repository can contribute is done: the project generates itself
on the cloud runner, the build number is handled, the scheme is shared, the
signing path is authored. What remains is a click-through in Xcode that nobody
but you can do.

**→ `docs/release/XCODE_CLOUD_RUNBOOK.md`, Stage 1.** If the Mac is already
gone, read "If you have to abandon Xcode Cloud" at the end of that file: GitHub
Actions already builds the same archive and the signing steps are written and
switched off.

---

## What is verified, and against what

> **2026-08-29 pre-submission audit.** A five-agent re-verification found and
> fixed, at SHA f89c0b4: six iOS defects a device would surface (a 60s session
> cap silently overriding the 90s chat timeout; a voice-note failure that
> promised the recording was kept while the recorder had deleted it; a file
> picker whose cancel wedged all imports; a 20-minute vault poll with no
> cancel; a cold-start stranding on a revoked session; a stray "--"), three
> backend logging bypasses (a production DEBUG file sink, diagnose tracebacks,
> an unscrubbed Sentry), four boot-validation gaps, rate-limit holes (a
> spoofable client IP, an unthrottled password endpoint), an ungated
> transcription spend, an unverifiable telegram registration, six filesystem
> stores account deletion never reached, and a cross-user report-file
> collision. Every fix is gated or tested. Open owner decisions are listed in
> the project memory and this run's report. **A new gate,
> `ci_scripts/ci_post_xcodebuild.sh`, now asserts every archive is
> upload-ready (Xcode 26 SDK, icon, assets, privacy manifest) — all prior
> ARTIFACT ticks were on Xcode 15.2 and are VOID for the uploadable archive
> until the device pass re-checks them.**
>
> The owner decisions were then resolved and CI was taken fully green:
> **all eight GitHub Actions jobs pass on SHA `c12ab47`** (python, postgres,
> web, android, ios-changes, ios, container, probe), including the backend
> suite on SQLite and PostgreSQL and the macOS iOS build and Core tests. The
> Telegram bot is disabled-and-gated for v1, chat-in-timeline and the
> error-monitoring provider are disclosed, locked-out recovery is
> support-mediated, and the invite wall is reworded. One decision is still
> open by choice: the governing-law clause is drafted and waiting on the
> owner's home state.

Three near-rejections this week — no bundle resources, no `CFBundleIconName`, a
placeholder app icon — all came from checking the **source** and calling it
verified. So every claim below now carries what it was actually checked against:

- **ARTIFACT** — the built `.app` or `.xcarchive`, or a screen of the running
  binary. This is the only tier that says anything about what ships.
- **LIVE** — a real request to production and the response read.
- **SOURCE** — the repository only. True of the code; says nothing about the
  build. **These are the ones that hid three defects.**

### The app itself

- **ARTIFACT — the shipping target builds and runs on this Mac.** Removing
  GoogleSignIn made it possible; it was the only reason a Swift 5.9 toolchain
  could not resolve the project.
- **ARTIFACT — the bundle contains what it must.** `Assets.car`,
  `PrivacyInfo.xcprivacy` at the bundle root, both icon PNGs, and a top-level
  `CFBundleIconName`. *Until 2026-08-27 none of this was true and nothing
  noticed, because the checks read `project.yml` instead of the `.app`.*
- **ARTIFACT — the built Info.plist**, key by key: bundle id, versions,
  `ITSAppUsesNonExemptEncryption`, `LSRequiresIPhoneOS`, orientations, the
  microphone string, and `THOUGHTPINS_API_BASE_URL` pointing at production.
- **ARTIFACT — the app icon is the real mark**, 1024×1024 at source with no
  alpha, fully opaque at every rendered size.
- **ARTIFACT — cold launch, both appearances.** Launch background samples
  #F2F2F7 light and #000000 dark, matching the settled page background exactly.
  No flash, no step. *The earlier measurement of this was void: it ran on a
  build where `LaunchBackground` was not in the bundle at all.*
- **ARTIFACT — a virgin `git clone` from GitHub archives.** Empty `$HOME`, the
  post-clone script run as Apple runs it, `CFBundleVersion` carrying the
  injected build number.
- **ARTIFACT — Release configuration behaves as Debug does.** The whole feature
  sweep, 15 steps, run with `-configuration Release`.
- **LIVE — both release levers fire.** Minimum raised: the update screen with
  both version numbers and a working store button. Maintenance: a banner with
  the app usable underneath.
- **LIVE — a single entry can be deleted**, and the assistant that could recite
  its content before could not after.
- **LIVE — account export produces a 135 KB file** through the share sheet.
- **ARTIFACT — the detail screens** passed the accessibility, iPad, Dynamic
  Type, light/dark, 375pt, offline, empty-state and error passes, with real
  injected 404s, 500s and dropped connections.

### The backend

- **LIVE — journal text and tokens reach no log line.** A sentinel driven
  through the running app at DEBUG. Found a real leak in the provider SDK.
- **LIVE — account deletion purges**, verified by walking every table in the
  database afterwards.
- **LIVE — registration works against production**, by registering and deleting
  a throwaway account.
- **SOURCE — spend is capped** at $3/user and $50/platform per month. The code
  enforces it before the provider is called and a deploy that disables it is
  refused, but **no request has ever been driven past the cap**. Untested.

### CI

- **ARTIFACT — seven jobs green**, `ios` included, with the archive and its
  dSYMs kept for 30 days, and the build number asserted inside the built binary.
- **ARTIFACT — the post-clone script itself is exercised on every run**, both
  build-number branches, from a clean checkout.

### Still SOURCE-only, and honestly so

These are true of the repository and have never been observed in the shipping
artifact. They are the remaining candidates for the same class of surprise:

- The spend cap has never been hit in anger.
- Keychain writes have never run under a **real** signature — only ad-hoc.
  Unsigned builds are refused by `SecItemAdd`, TestFlight builds should not be,
  and no build in between has been tested.
- Sign in with Apple ships as an entitlement with no button. Reasoned inert;
  never observed on a signed build.
- The privacy manifest's contents have never been reconciled against what Apple
  actually asks at upload — only its presence in the bundle is checked.

---

## What is deferred to the device pass

`docs/release/DEVICE_TEST_SCRIPT.md` — ten tests, written before the build
exists, each with steps, expected results and failure criteria. None can be done
in a simulator:

launch background colour on iOS 26 · microphone denied · microphone revoked
while running · a call interrupting a recording · real Split View and Slide Over
· Dynamic Type via Settings · VoiceOver by gesture · airplane mode mid-session ·
the detail screens on hardware · cold launch after force-quit and after reboot.

Screenshots: the current sets are valid to submit. The 6.9" slot is 1320 × 2868
and an iPhone 17 Pro Max produces it natively, so capture the final set from
TestFlight if you want the upgrade. The iPad A16 is 1640 × 2360, which is **not**
a listed App Store size — do not plan iPad screenshots from it.

---

## What remains for the PC

In order.

1. **Xcode Cloud Stage 1**, if the Mac still exists. Otherwise the Actions
   fallback.
2. **Stage 0 of the runbook** — register the bundle id, **enable Sign in with
   Apple on the App ID** (the entitlement ships; automatic signing fails without
   the capability, with an error that talks about provisioning), create the app
   record.
3. **Turn on Railway database backups and write down that you did.** Nothing in
   the repository backs up the production database. Whether the data is
   recoverable today depends on a dashboard setting nobody has recorded. This is
   the highest-value item on this list and it is a toggle.
4. **Set `IOS_STORE_URL`** once the listing exists. `store_urls.ios` is null, so
   the update screen currently falls back to "search the App Store".
5. **Set `RECOMMENDED_IOS_VERSION=1.0.0` explicitly.** It falls back to
   `API_VERSION`, which is `1.0.0-rc.1` on production right now. A deploy is now
   refused while it is that shape, but the variable still wants setting.
6. **Twenty minutes of monitoring** — `docs/operations/LAUNCH_OPERATIONS.md` §2.
   Nothing alerts a human today. Free.
7. **Nothing here.** The published-page scoping is done, and single-entry
   deletion shipped rather than being scoped away.

---

## Decisions, and why

**GoogleSignIn removed from v1.** The button never rendered — the app refuses a
third-party login without Sign in with Apple beside it (4.8), and Apple sign-in
is not configured — and the provider read two Info.plist keys that do not exist,
so it could only ever throw. It was a linked SDK for an unreachable feature, and
the only thing stopping this Mac building the app. Recoverable from git history;
`ios_release.sh` still knows how to build a Google-enabled archive.

**Mature age rating.** Unmoderated generative text with no ceiling we impose.
Every premise re-checked against the build. The route to a lower tier is a
moderation layer we own, not a re-answered questionnaire.

**No crash SDK.** After the GoogleSignIn removal the iOS app has zero
third-party dependencies. Xcode Organizer gives symbolicated crash reports free,
the dSYMs are correct and retained, and adding an SDK would change what must be
declared on the privacy questionnaire. Revisit only if Organizer proves
inadequate.

**`PRIVATE_ALLOW_LLM` stays off.** Entries marked private are never sent to a
third-party model. That is the stronger claim; the lead screenshot was reframed
so a refused control is not its subject.

**`SYSTEM_LOCKED` keeps its closed default.** Right for a fresh self-hosted
install, wrong for production — so the pre-deploy check refuses a production
deploy that leaves it on, and `smoke_registration.py` proves registration works
after a deploy, which config validation cannot.

---

## Known gaps, honestly

- **No production database backup in the repo.** See item 3 above.
- **Rollback is UNREHEARSED.** No Railway CLI on this machine. The procedure is
  written from the code and the provider's documented behaviour; the first
  person to run it should confirm and correct
  `docs/operations/LAUNCH_OPERATIONS.md` §1.
- **Migration downgrades have never run against PostgreSQL.** All 26 define real
  `downgrade()` bodies, but CI exercises them on SQLite, where every
  PostgreSQL-only branch is skipped. Prefer rolling forward.
- **Three published feature descriptions now name the web app** — manage
  devices, search, routing undo. The fourth, privacy's "delete specific content
  ... from the app", was a stated right rather than a description, so the app
  was changed to honour it instead of scoping the sentence.
  `WEB_IOS_PARITY.md`.
- **The person-card promise is loose.** A "when you last spoke" phrasing does
  not match the screen, which shows *Last mentioned* (when you last wrote about
  them). The listing copy in `APP_STORE_METADATA.md` avoids the phrase; do not
  reintroduce it.
- **Three worker-recovery tests fail locally** for want of a broker URL. They
  fail identically at `HEAD` before this session's work and pass with
  `REDIS_URL` set.
- **The local gate cannot run three steps** — SBOM, approval tilt, frontend
  audit — because this Mac has no Node. They pass in CI.
- **The simulator UI tests are not in the repository.** They carry the review
  account's password inline, and `AGENTS.md` keeps credentials out of source
  control. They are a local harness; CI covers the archive.

---

## If the first Xcode Cloud build failed, check these in order

Open the failed build, click the failing step, **Download Logs**, search for the
string in bold. Stop at the first match.

**1. Signing — by far the most likely.** Search **`Provisioning`**.

A match means Sign in with Apple is not enabled on the App ID. The entitlement
ships in the binary and automatic signing cannot create a profile for a
capability the App ID lacks; the message talks about provisioning, not
entitlements, which is why it is not obvious. Fix at
developer.apple.com/account → Identifiers → `com.thoughtpins.app` → tick **Sign
in with Apple** → Save, then re-run. One wasted build.

**2. The post-clone script never ran.** Search **`ci_post_clone`**.

*No match at all* is the signal. If the log never says `==> ci_post_clone:
preparing`, Xcode Cloud did not find the script, and everything after fails
looking for a project that was never generated. Check:
`git ls-tree -r HEAD mobile/ios/ThoughtPinsNative/ci_scripts/` — it must show
mode `100755`.

**3. Something the cloud could not see.** Search **`ARCHIVE FAILED`** and read
the first `error:` above it.

The cloud clones a virgin copy: no working tree, no caches, no generated
project. A fresh `git clone` was archived on 2026-08-27 and succeeded, so this
is unlikely — but if it appears, reproduce it the same way rather than on this
Mac, because this Mac has state the cloud does not.

**The one line to find first, every time:**

```
==> ci_post_clone: done in
```

Present → the project generated, the scheme is shared, the build number was
stamped, and the failure is downstream: almost certainly signing.
Absent → nothing was built at all, and it is cause 2 or 3.

**Before spending a second cloud build**, check GitHub Actions for the same
commit. It runs the identical post-clone script, both build-number branches, and
the same archive. Actions green + cloud red = signing or account, never the
script and never the code.

### What was fixed the night before, so you know it is not these

- **The archive contained no resources at all** — no `Assets.car`, no
  `PrivacyInfo.xcprivacy`, no icon — because `project.yml` declared them under a
  `resources:` key XcodeGen does not have. Two certain rejections and a blank
  icon. Fixed and gated.
- **No top-level `CFBundleIconName`** — ITMS-90713. Fixed and gated on both the
  source plist and the built app.
- **Chat timed out on a working reply.** Production answers `/v1/chat` in
  13–22s against what was a 30s timeout. Chat now gets 90s; the global timeout
  is unchanged, because it is what distinguishes an unreachable server from a
  slow one.
- **The committed evidence screenshots are of the wrong build.** Before the
  asset catalog shipped there was no `AccentColor`, so every control outside the
  signed-in shell rendered in system blue; they are orange now. The two files in
  `screenshots/evidence/` show blue and should be recaptured. The twelve store
  screenshots are unaffected — they contain no system blue, because the
  signed-in screens were already tinted explicitly.
