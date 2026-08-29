# Xcode Cloud runbook — for a Windows machine with no Mac

Written for one person, alone, on a PC, with no memory of how any of this was
set up. Follow it in order. Nothing here assumes you have a Mac, **except
Stage 1**, which must be done on a Mac before you lose access to one.

Everything is a website: [App Store Connect](https://appstoreconnect.apple.com),
[the developer portal](https://developer.apple.com/account), and GitHub. None
of it needs Xcode after Stage 1.

---

## The one thing that cannot wait

**Xcode Cloud's first setup can only be done from Xcode, on a Mac.**

Apple's documentation is explicit: *"Use Xcode to initially configure your
project or workspace to use Xcode Cloud. After you complete your first build,
use either Xcode or App Store Connect to configure additional workflows, access
build information, and more."*

There is no way around it:

- The App Store Connect **API cannot create a product**. `ciProducts` supports
  read and delete only; `ciWorkflows` can be created, but only underneath a
  product that already exists.
- The App Store Connect **website** shows an Xcode Cloud tab on an app that has
  already been onboarded, and lets you edit workflows there. It does not do the
  first onboarding.

So Stage 1 happens on the Mac, once. Everything afterwards is a browser.

---

## Stage 0 — before you touch Xcode (10 minutes, can be done from the PC)

These are prerequisites the repository cannot contain, because they are account
state. Do them first; Stage 1 fails confusingly without them.

1. **Confirm the developer account is active.** developer.apple.com/account →
   Membership. You need the Team ID, a 10-character string like `A1B2C3D4E5`.
   Write it down; you will need it more than once.

2. **Register the bundle identifier.** developer.apple.com/account →
   Certificates, Identifiers & Profiles → Identifiers → **+** → App IDs → App.

   - Description: `Thought Pins`
   - Bundle ID: **Explicit** — `com.thoughtpins.app` (exactly this; it is set in
     `mobile/ios/ThoughtPinsNative/project.yml` and asserted by a gate)

3. **Enable Sign in with Apple on that App ID — and nothing else.** Same screen,
   Capabilities list, tick **Sign in with Apple**, Save.

   **The exact list is one item.** `ThoughtPins.entitlements` declares exactly
   one entitlement, `com.apple.developer.applesignin`, and the Info.plist
   declares no background modes, no push, no iCloud and no app groups. Every
   capability you tick is another thing automatic signing must provision and
   another way the first build can fail, so tick that one and stop.

   I could not check the portal from here — it needs your account — so treat
   this as the specification rather than a report: if the App ID already exists,
   open it and confirm Sign in with Apple is on and nothing else is.

   This is not optional and it is the single most likely cause of a first build
   failing at signing. `mobile/ios/ThoughtPinsNative/Resources/ThoughtPins.entitlements`
   declares `com.apple.developer.applesignin`, the project signs automatically,
   and automatic signing cannot create a profile for an entitlement the App ID
   does not have. The error you would get is about provisioning, not about
   entitlements, which is why it is worth doing now.

   (The feature is not offered in v1 — the app hides the button until Apple
   sign-in is configured — but the entitlement ships, deliberately, so turning
   it on later is a server setting rather than a new build.)

4. **Create the app record.** appstoreconnect.apple.com → Apps → **+** → New App.

   - Platform: iOS
   - Name: `Thought Pins`
   - Primary language: English (U.S.)
   - Bundle ID: pick `com.thoughtpins.app` from the list
   - SKU: `thoughtpins-ios-001` (any stable string; never shown to users)
   - User Access: Full Access

   You need the App Manager, Admin or Account Holder role to do this. If you
   only have Developer, you need the "Create Apps" permission.

---

## Stage 1 — on the Mac, once (20 minutes) — **CANNOT BE DONE LATER**

> If you are reading this on a PC and Stage 1 was never done, stop. You need a
> Mac with Xcode. Everything below Stage 1 depends on it.

1. **Sign the paid account into Xcode.** Xcode → Settings → Accounts → **+** →
   Apple ID. Sign in with the Apple ID that holds the developer membership.

   **This Mac is currently signed in with a free Personal Team**, `W24H269428`,
   which cannot create the App Store Connect product Xcode Cloud needs. Adding
   the paid Apple ID is genuinely step one.

   **How to verify it took, two ways:**

   In the GUI — Xcode → Settings → Accounts, select the Apple ID, and read the
   **Team** list on the right. You want a row whose Type is **App Store** (or
   *Company/Organization*). A row reading **Personal Team** is the free one and
   is not enough.

   In the terminal, which is unambiguous:

   ```bash
   defaults read com.apple.dt.Xcode IDEProvisioningTeams
   ```

   Each team prints `isFreeProvisioningTeam`. You need at least one entry where
   that is **0**. If every entry says `1`, the paid membership has not reached
   Xcode: sign out and back in, or confirm the membership is on that Apple ID at
   developer.apple.com/account. Today this machine prints a single team with
   `isFreeProvisioningTeam = 1`.

2. **Generate and open the project.**

   ```bash
   cd mobile/ios/ThoughtPinsNative
   xcodegen generate            # the .xcodeproj is not in git; this creates it
   open ThoughtPins.xcodeproj
   ```

3. **Select the team.** Project navigator → ThoughtPins target → Signing &
   Capabilities → Team → the paid team. "Automatically manage signing" stays
   ticked.

4. **Start Xcode Cloud onboarding.** Report navigator (⌘9) → the **Cloud**
   button at the top → **Get Started**.

5. **Select the product.** Xcode lists what it found. Choose **ThoughtPins**.
   Next.

6. **Review the workflow, then edit it.** Click **Edit Workflow** and set it up
   as described in Stage 2 below. You can also accept the default and fix it
   later from the website — the important thing is getting past onboarding while
   you have a Mac.

7. **Grant access to the repository.** Xcode sends you to App Store Connect and
   then to GitHub to authorise the Xcode Cloud app for `seramasamy/thoughtpins`.
   Grant it.

8. **Start the first build.** Choose branch `main`, click **Start Build**.

9. **Confirm it appears on the website.** appstoreconnect.apple.com → Apps →
   Thought Pins → **Xcode Cloud** tab. If you can see the build there, the
   handoff is complete and the Mac is no longer required.

**Write down, before leaving the Mac:** the Team ID, the workflow name, and
that the product is called ThoughtPins.

---

## Stage 2 — the workflow, configured to spend as little as possible

Xcode Cloud gives **25 compute hours a month**. The goal is that the first cloud
build is a real build, not a debug session, and that no setting quietly
multiplies compute. Every choice below is made for that.

Set these in the wizard during Stage 1, or afterwards at App Store Connect →
Apps → Thought Pins → Xcode Cloud → Manage Workflows.

### Start condition — manual only

Delete whatever start condition the wizard proposes. It defaults to **Branch
Changes**, which builds on every push to `main` and is exactly how an allowance
disappears.

In the workflow editor: **Start Conditions** → select the existing condition →
**Delete**. Then **+** → **Manual**. You will have one condition, reading
*Manual*.

Nothing is lost. GitHub Actions already builds an unsigned archive of every
push to `main` that touches iOS, keeps it 30 days, and runs the same post-clone
script. Xcode Cloud is only for builds you intend to send to TestFlight.

### One action: Archive

Delete any **Test** or **Analyze** action the wizard adds.

**What you lose: nothing that is not already covered.** `swift test` on
ThoughtPinsCore — 65 tests — runs on Actions on every iOS-touching push to
`main`, along with the unsigned archive, the built-Info.plist check and the
build-number assertion. A Test action here would re-run those on the expensive
runner, and it would need a simulator destination, which is its own multiplier.

The Archive action's settings:

| Field | Value | Why |
|---|---|---|
| Platform | **iOS** | Not "iOS + iPadOS + macOS". The app is one platform; extra platforms are extra builds |
| Scheme | **ThoughtPins** | Generated as a *shared* scheme; the post-clone script fails loudly if it is ever missing |
| Configuration | **Release** | Comes from the scheme's archive action already |
| Deployment Preparation | **TestFlight (Internal Testing Only)** | Widen later; external testing needs review |

### What silently multiplies compute

- **Multiple platforms on one action.** Each is a separate build. iOS only.
- **A Test action with more than one simulator destination.** Each destination
  is a separate run of the whole suite. You have no Test action, so this cannot
  bite — keep it that way.
- **Branch and pull-request start conditions together.** A PR from a branch that
  also pushes builds twice.
- **"Automatically manage" Xcode version** is fine and is not a multiplier.

### Xcode version — where it is set

Workflow editor → **Environment** → **Xcode Version**. Pick **Latest Release**,
not a specific older version and not a beta.

Reasons: App Store uploads have required Xcode 26+ since 28 April 2026, so an
older selection cannot produce an uploadable build; and betas can change
behaviour between builds. macOS Version beneath it: leave whatever pairs with
that Xcode.

### TestFlight — a post-action, not a separate action

It is a **post-action on the Archive action**, and that is what you want.

Workflow editor → the Archive action → **Post-Actions** → **+** → **TestFlight
Internal Testing** → choose your internal group.

Cost: **effectively nothing.** A post-action runs inside the same build, and
uploading is network time on an already-running machine, not a second build.
Making distribution a separate action or a second workflow would mean a second
archive, and that is a second billed build.

## What the post-clone script costs, measured

This runs on every cloud build and its wall clock is billed, so it was measured
rather than guessed — on a `macos-latest` runner, which is the closest available
proxy for a cold Xcode Cloud machine.

| | Seconds |
|---|---|
| `ci_post_clone.sh` end to end, first run | **1** |
| Same script, second run (XcodeGen already unpacked) | **0** |
| Pinned XcodeGen download + unzip | **1** |
| `brew install xcodegen`, formula index already present | **2** |

**The install method does not matter for speed.** One second against two, on a
script that is 1s of a build measured in minutes. Anyone claiming a meaningful
saving here is guessing.

The pinned download is kept for two reasons that are not speed:

- **It needs only `curl` and `unzip`,** which exist on any macOS machine.
  Homebrew may not be installed on a cloud runner at all, and `brew install` can
  trigger a formula-index update that is far slower than the 2s measured here,
  where the index was already warm.
- **The version is exact.** `2.46.0` produces the same project on the cloud as
  on a Mac. A formula that moves would not.

Homebrew remains the fallback inside the script if the download is ever blocked.

**Package resolution is close to zero and gated to stay that way.** With
GoogleSignIn gone there are no remote Swift packages anywhere in the graph:
`ThoughtPinsApp` depends on `../ThoughtPinsCore` by path, `ThoughtPinsCore`
depends on nothing, `project.yml` declares no `url:`, and no `Package.resolved`
is tracked. `scripts/check_ios_submission_source.py` fails the build if a remote
package is ever added, because that would make a clean build depend on someone
else's uptime and add billed resolution time to every run.

---

## Stage 3 — what the cloud needs, and where each thing comes from

Walked end to end, so nothing is discovered late. Everything marked *repo* needs
no action from you.

| Input | Where it comes from | Action |
|---|---|---|
| Xcode project | **Generated** by `ci_scripts/ci_post_clone.sh` on every build. The `.xcodeproj` is gitignored on purpose so two machines cannot produce conflicting pbxproj diffs. | none |
| `ci_scripts` location | `mobile/ios/ThoughtPinsNative/ci_scripts/` — beside the project, which is where Apple requires it | none |
| Script permissions | committed `100755` with a `#!/bin/sh` shebang, asserted by `scripts/check_ios_submission_source.py` | none |
| Shared scheme | `ThoughtPins`, generated; the post-clone script refuses to continue without it | none |
| Bundle identifier | `com.thoughtpins.app` in `project.yml` *(repo)* | must match the App ID from Stage 0 |
| Deployment target | iOS 17.0 *(repo)* | none |
| Device family | iPhone and iPad *(repo)* | none |
| Entitlements | `Resources/ThoughtPins.entitlements` → Sign in with Apple *(repo)* | **capability must be on the App ID** (Stage 0 step 3) |
| Team / signing | Not in the repo, deliberately — signing material never is. Xcode Cloud signs automatically using the team that owns the product. | none after Stage 1 |
| Build number | `CI_BUILD_NUMBER`, stamped into `project.yml` by the post-clone script before generating. Falls back to the commit count when that variable is absent, so a local run and Actions also produce a real number. Both branches are exercised on every Actions run of the `ios` job | none |
| Marketing version | `MARKETING_VERSION: 1.0.0` in `project.yml` *(repo)* | bump by hand for 1.1 |
| `THOUGHTPINS_API_BASE_URL` | A **build setting** in `project.yml`, expanded into Info.plist at build time — not an environment variable *(repo)* | none |
| Export compliance | `ITSAppUsesNonExemptEncryption = false` in Info.plist *(repo)* | none |
| Environment variables | **None required.** Do not add any. | none |
| Secrets | **None required.** The cloud signs with the account; nothing is passed in. | none |

If a build ever asks you for something not on this list, that is new — write it
down before changing anything.

### Anything that would fail on a runner which has never built this repo

Checked deliberately, because a cold machine is the one case a local Mac never
reproduces:

- **`project.yml`** sets `CODE_SIGN_STYLE: Automatic` and no `DEVELOPMENT_TEAM`.
  That is correct for Xcode Cloud, which supplies the team from the product.
  There is no path in it to anything outside the repository, no absolute path,
  and no tool beyond XcodeGen.
- **`ExportOptions.plist`** carries `TEAM_ID_PLACEHOLDER` rather than a real
  Team ID. Nothing in the Xcode Cloud path reads that file — it exists for the
  GitHub Actions signing path, which substitutes the value from a secret. If you
  ever run `xcodebuild -exportArchive` by hand, substitute it first or the
  export fails on a placeholder.
- **The post-clone script** installs XcodeGen into `$HOME`, which exists and is
  writable on any runner, and needs only `curl`, `unzip` and `git`. It does not
  assume Homebrew, a warm cache, or a particular working directory.
- **No remote Swift packages**, so nothing resolves over the network and a
  GitHub or vendor outage cannot fail the build.

---

## Stage 4 — the first build, and reading it

1. App Store Connect → Thought Pins → Xcode Cloud → **Start Build** (or push to
   `main`).
2. Watch the build. Expect roughly 10–20 minutes.
3. The steps you will see, in order: *Clone* → *Post-clone script* → *Resolve
   dependencies* → *Archive* → *TestFlight*.

**Where the logs are.** Click the build, then any step in the left column. The
log pane is on the right. **Download Logs** at the top right gives you the whole
thing as a text file, which is easier to search.

**Read the post-clone step first.** It prints what it did, and every failure it
raises explains itself:

```
==> ci_post_clone: preparing /Volumes/workspace/repository/mobile/ios/ThoughtPinsNative
    CI_BUILD_NUMBER:   42
==> installing XcodeGen 2.46.0
==> setting CURRENT_PROJECT_VERSION to 42
==> generating ThoughtPins.xcodeproj
==> ci_post_clone: done
```

If that block is missing entirely, Xcode Cloud never found the script — see the
first row of the failure table below.

---

## Recognising a first-build failure in thirty seconds

Assume the first cloud build fails. These are the three most likely reasons, in
order, with exactly what to look for. Open the failed build, click the failing
step, **Download Logs**, and search for the string in the middle column.

| # | Reason | Search the log for | What it means and what to do |
|---|---|---|---|
| 1 | **Sign in with Apple not on the App ID** | `Provisioning profile` or `doesn't support the Sign In with Apple capability` or `No profiles for 'com.thoughtpins.app'` | Automatic signing cannot make a profile for an entitlement the App ID lacks. The message talks about *provisioning*, not entitlements, which is why it is first here. Fix: Stage 0 step 3, then re-run. Costs one wasted build |
| 2 | **The post-clone script did not run** | `ci_post_clone` — its **absence** is the signal | If the log has no `==> ci_post_clone: preparing` line at all, Xcode Cloud never found the script, and the next failure will be "no such file or directory" from xcodebuild looking for a project that was never generated. Check `git ls-files -s mobile/ios/ThoughtPinsNative/ci_scripts/` prints mode `100755` |
| 3 | **The scheme is not shared** | `ci_post_clone FAILED: no shared scheme` or `Scheme ThoughtPins not found` | The script checks for this itself and fails with the first message, deliberately, rather than letting xcodebuild produce the second. Means `project.yml`'s `schemes:` block changed |

**The one line to find first, every time.** Search the post-clone step for:

```
==> ci_post_clone: done in
```

If that line is present, the project generated, the scheme is shared and the
build number was stamped — so the failure is downstream, and it is almost
certainly signing (row 1). If it is absent, the failure is the script or its
location (rows 2 and 3), and nothing was built at all.

**Before spending a second cloud build on any of this**, check GitHub Actions
for the same commit. It runs the identical post-clone script on every push to
`main` that touches iOS. If Actions is green and the cloud is red, the problem
is signing or the account — never the script, never the project generation, and
never the code.

---

## Stage 5 — when a build fails

Work down this table. The first column is what you will actually see.

| What you see | What it means | What to do |
|---|---|---|
| `Post-Clone script not found at ci_scripts/ci_post_clone.sh` | The script is not where Xcode Cloud looks, or is not committed | It must be at `mobile/ios/ThoughtPinsNative/ci_scripts/ci_post_clone.sh`, beside the `.xcodeproj`. Run `git ls-files -s mobile/ios/ThoughtPinsNative/ci_scripts/` — it must print mode `100755` |
| Post-clone runs but fails oddly, or `command not found` | The script lost its executable bit, so Apple ran it under `zsh` and ignored the shebang | `git update-index --chmod=+x mobile/ios/ThoughtPinsNative/ci_scripts/ci_post_clone.sh`, commit, push. `python scripts/check_ios_submission_source.py` catches this before you push |
| `ci_post_clone FAILED: XcodeGen is not installed` | GitHub or Homebrew was unreachable from the runner | Almost always transient. Re-run the build |
| `ci_post_clone FAILED: no shared scheme` | The `schemes:` block in `project.yml` changed | Restore it; Xcode Cloud can only build shared schemes |
| `No profiles for 'com.thoughtpins.app' were found` / any provisioning error | Usually **Sign in with Apple is not enabled on the App ID** | Stage 0 step 3. Then re-run |
| `The bundle identifier ... is not available` | The App ID was never registered, or belongs to another team | Stage 0 step 2 |
| Archive succeeds, TestFlight step fails with a duplicate build number | Two builds produced the same `CFBundleVersion` | Should not happen — the number is `CI_BUILD_NUMBER`. Check the post-clone log printed `setting CURRENT_PROJECT_VERSION to <n>`. If it printed `CI_BUILD_NUMBER is unset`, the workflow is misconfigured |
| Swift compile errors | A real code problem | GitHub Actions builds the same archive on every push to `main` that touches iOS — check there first, the logs are easier to read |
| Everything green, no build in TestFlight | Processing takes 5–15 minutes after upload, and export compliance can hold it | App Store Connect → TestFlight → Builds. If it says "Missing Compliance", answer it there; `ITSAppUsesNonExemptEncryption=false` should prevent that |

**Before debugging a cloud build at all**, check whether GitHub Actions is
green: it builds an unsigned archive of the same commit and keeps it for 30
days. If Actions is red too, the problem is the code, and Actions logs are far
easier to read. If Actions is green and the cloud is red, the problem is
signing, the account, or the post-clone script.

---

## Stage 6 — getting a build to a tester

1. App Store Connect → Thought Pins → **TestFlight** → Builds → iOS.
2. Wait for the build to leave "Processing".
3. If prompted, answer export compliance: **No**, the app does not use
   non-exempt encryption. (Standard HTTPS only.)
4. **Internal Testing** → your group → **+** next to Builds → pick the build.
5. Testers get an email. Install TestFlight on the device, then the build.

Internal testers (up to 100, must be on your team) need no review. External
testing does need a review, and is a separate, slower thing — do not start
there.

---

## What is still manual, and what it costs

- **Xcode Cloud's free tier** is 25 compute hours a month. A build of this app
  is roughly 10–20 minutes, so that is dozens of builds. Watch it in App Store
  Connect → Xcode Cloud → Usage.
- **The App Store submission itself** — screenshots, description, age rating,
  review notes — is all in App Store Connect and needs no Mac. Everything you
  need is in `apple-submission/`.
- **The device test pass** in `docs/release/DEVICE_TEST_SCRIPT.md` needs the
  physical devices, not a Mac. Do it against the first TestFlight build.

---

## If you have to abandon Xcode Cloud

GitHub Actions already builds an **unsigned** archive of every commit to `main`
that touches iOS, and keeps it with its dSYMs for 30 days. The signing and
upload steps are written and switched off in `.github/workflows/ci.yml`; turning
them on needs six secrets, listed in a comment beside them. That is the
fallback if Xcode Cloud proves unworkable — it is not the primary path, because
it needs signing material in a repository secret, and Xcode Cloud does not.

**Treat the signed Actions path as untested.** The unsigned archive is proven
on every push; the signed export and App Store upload steps have never run
end to end from this Mac-less setup. Two things in particular are unverified:
the export needs a signing certificate and a distribution profile minted from a
PC (Apple's Developer portal can export a `.p12` and a profile, but nobody has
done it here), and the `-allowProvisioningUpdates` export now passes an App
Store Connect API key so it can create a profile headlessly — plausible, not
demonstrated. Expect to iterate on the first real run. Xcode Cloud avoids all
of this because Apple signs on their infrastructure.
