# Submission status — Thought Pins 1.0.0

**Last updated:** 2026-08-26, at the end of the final Mac session.
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

## What is verified

Verified means a command was run and its output read, or a screen was looked at.
Not "the code looks right".

### The app itself

- **The shipping app target builds and runs on this Mac** — for the first time.
  Removing GoogleSignIn made that possible; it was the only reason a Swift 5.9
  toolchain could not resolve the project. Every earlier verification ran
  against a scratch copy outside the repository.
- **The real binary was checked, not a stand-in:** committed Info.plist, bundle
  id `com.thoughtpins.app`, portrait-only iPhone and all-four iPad, no Google
  keys or URL types surviving into the built plist, no embedded frameworks,
  5.9 MB, and a launch that resolved `https://api.thoughtpins.com` from its own
  Info.plist and got 200 from `/v1/client-config` over HTTP/2.
- **Both release levers fire.** With the minimum raised, the app shows "Update
  Thought Pins to continue", both version numbers, and a working store button;
  put back, it returns to normal. Maintenance mode shows its message as a banner
  with the app usable underneath — not a dead screen.
- **Account export gives you a file.** 135 KB JSON through the share sheet, with
  Save to Files. It previously fetched the payload and discarded it while saying
  "Your export is ready."
- The detail screens have had the accessibility, iPad, Dynamic Type, light/dark,
  375pt, offline, empty-state and error passes; errors and offline were driven
  with real injected 404s, 500s and dropped connections.

### The backend

- **Journal text and tokens reach no log line.** Driven with a sentinel through
  the real app at DEBUG, asserted across every logger. This found a real leak —
  the model provider's SDK logs the full prompt at DEBUG — now clamped
  regardless of `LOG_LEVEL`.
- **Account deletion purges.** Walked every table in the schema after a real
  deletion: nothing owned by the user survives, and the journal text is gone
  from every column. The user row remains as an anonymised tombstone, which is
  deliberate; it no longer keeps the account's settings.
- **Registration works against production**, proven by a check that registers a
  throwaway account, asserts it is admitted, and deletes it.
- **Spend is capped**: $3/user/month and $50/platform/month, enforced before the
  provider is called. A production deploy that would silently disable that is
  now refused.

### CI

Seven jobs green on an ordinary push to `main`, `ios` included. Build number is
the commit count, asserted against the built binary. Archive and dSYMs kept 30
days. Signing and upload steps authored and skipped until secrets exist.

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
7. **Scope four sentences** on the published pages, or accept them —
   `docs/release/WEB_IOS_PARITY.md`, last section. They are true of the web app
   and not of iOS, and the listing is the iOS listing.

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
- **Four published promises are web-only** — manage devices, search, delete
  specific content, undo. `WEB_IOS_PARITY.md`.
- **The person-card promise is loose.** The listing says "when you last spoke";
  the screen shows *Last mentioned*, which is when you last wrote about them.
  No field was invented to make the copy true — change the sentence.
- **Three worker-recovery tests fail locally** for want of a broker URL. They
  fail identically at `HEAD` before this session's work and pass with
  `REDIS_URL` set.
- **The local gate cannot run three steps** — SBOM, approval tilt, frontend
  audit — because this Mac has no Node. They pass in CI.
- **The simulator UI tests are not in the repository.** They carry the review
  account's password inline, and `AGENTS.md` keeps credentials out of source
  control. They are a local harness; CI covers the archive.
