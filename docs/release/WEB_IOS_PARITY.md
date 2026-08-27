# Web and iOS parity

Nobody had looked at this. The privacy policy, terms and support pages describe
one product; the App Store listing describes one product; there are two clients.
This is what each one actually does, which divergences were chosen, and which
were not.

Read alongside `apple-submission/REVIEW_NOTES.md`. **The listing is the iOS
listing**, so anything true on the web and not on iOS is the direction that gets
a submission rejected — those are called out first.

Verified 2026-08-26 by reading both clients end to end.

---

## Capabilities

| Capability | Web | iOS | Verdict |
|---|---|---|---|
| Write a note | yes | yes | parity |
| Voice note | yes | yes | parity |
| File import | yes | yes | parity |
| Obsidian vault import | yes | yes | parity (iOS lacks the conflict-policy picker) |
| Chat | yes | yes | **divergent** — web keeps a transcript, iOS shows only the latest reply |
| Response styles | yes | yes | parity |
| Importance prompts | yes | yes | parity |
| Private-memories toggle | yes | yes | parity |
| Recap day/week/month | yes | yes | parity |
| People cards | yes | yes | parity |
| Places cards | yes | yes | parity |
| Pins / library list | yes | yes | parity |
| Library source detail | yes | yes | parity |
| Memory card detail | yes | yes | parity |
| Account export | yes | yes | **fixed this pass** — see below |
| AI-processing consent | yes | yes | **fixed this pass** — version comparison |
| Account deletion | yes | yes | parity in effect, divergent in friction |
| Invite redemption | yes | yes | parity |
| Report a reply | standalone form | per-reply only | divergent, scoped |
| Voice archive | yes | yes | parity |
| Sign in: email/password | yes | yes | parity |
| Sign in: Apple | yes | yes | parity (both gated off by server config) |
| Sign in: Google | yes | hidden | intentional — 4.8 |
| Sign in: magic link | yes | **absent** | intentional |
| Manage sign-in methods | yes | **absent** | accidental, deferred |
| Devices / sessions | yes | **absent** | accidental, doc corrected |
| Delete a single entry | yes | **absent** | accidental, deferred |
| Search | yes | **absent** | accidental, deferred |

---

## Fixed in this pass

**Account export gave you nothing.** `exportAccount()` fetched the payload and
discarded it, then said "Your export is ready." The privacy policy promises
export "from the app" and the review notes send a reviewer to that button. It
now writes a JSON file and offers the system share sheet; verified on the
shipping binary against production (135 KB, Save to Files).

**Consent never re-prompted on a version bump.** Web compares the stored
acceptance version against the served `LEGAL_DOCUMENT_VERSION`; iOS only checked
that *an* acceptance existed. The day that version moves, every web user would
be re-prompted and no iOS user ever would. iOS compares versions now.

**Rate-limited refresh logged web users out.** Any refresh failure cleared the
session, so a 429 — five auth requests a minute per IP, which is one office
behind one NAT — signed people out with valid credentials. Only 401 and 403 end
a session now, which is the rule iOS already followed deliberately.

**Three iOS strings that were untrue.** A 429 on chat said "Chat failed"; a
rate-limited save called itself an offline draft with full signal; the in-app
safety report sent a 2000-character summary into a field the server caps at 1000
and therefore always failed.

---

## Divergences that are intentional and defensible

**Google sign-in is hidden on iOS.** The app refuses a third-party login unless
Sign in with Apple is offered beside it (Guideline 4.8), and Apple sign-in is
not configured yet. Web has no such rule. The GoogleSignIn SDK was removed from
the iOS build entirely this session, because it could never be reached.

**No magic-link sign-in on iOS.** Passwordless email sign-in on a phone means
leaving the app for a mail client and returning through a URL callback. It is a
real feature, not an oversight, and it is not v1.

**Deletion friction differs.** Web makes you type `DELETE`; iOS uses a
confirmation dialog. Both end at the same server call with the same required
confirmation string. Typing a word on a phone keyboard is friction of a
different kind, and platform conventions differ. Both satisfy 5.1.1(v).

**Chat has no transcript on iOS.** Web keeps a scrollable thread; iOS shows the
latest reply. This is a real product difference and the review notes describe
the iOS behaviour accurately. Adding a transcript needs a message-list model the
app does not have — deliberately deferred, not accidental.

**iOS caps uploads at 25 MB client-side; web does not.** iOS is the stricter and
more honest of the two: it refuses before reading the file. The gap is that
**web** has no guard and will base64-encode a 30 MB file in the browser before
the server rejects it. Web is the one that should change.

---

## Divergences that nobody chose

These are accidental. None is fixed here; each is recorded with its cost.

**No way to delete a single entry on iOS.** `deleteEntry` exists in the core
client with no caller. The privacy policy says users can "delete specific
content ... from the app", and two dependent promises hang off it (deleting an
entry removes its retained recording; voice transcripts remain journal content
until the entry is deleted). *Cost: a swipe action on the Recap list plus a
confirmation — perhaps half a day. This is the most substantive accidental gap.*

**No devices or sessions screen on iOS.** The support page says to use the app's
Account screen to "manage devices". `registerDevice`, `revokeDevice`, `sessions`
and `revokeSession` all exist in the core client, uncalled. *Cost: the support
page should be scoped to the web app now — editorial. The screen itself is a
day.*

**No search on iOS.** Terms lists search as a feature. The memory-cards endpoint
takes a query parameter that iOS always sends empty. *Cost: a search field
bound to the existing parameter is small; scoping the terms wording is smaller.*

**Six of nine preference fields are unreachable on iOS** — preferred name,
timezone, reminder hour, notification settings. The request struct, the API
method and the response decode all exist and are exercised. *Cost: rows in an
existing Form. The cheapest item here.*

**No way to set or change a password on iOS**, or to see which sign-in providers
are attached. *Cost: moderate; needs its own screen.*

**Text length caps.** The server caps entries and chat at 50,000 characters and
web mirrors it in three composers. iOS has no cap on the live send path, so a
long entry gets a 422 and then falls into the draft queue, which refuses it too.
*Cost: one `maxLength` equivalent and a counter — small, but it needs the
draft-queue path checked with it.*

**Error wording diverges throughout.** Web renders the server's envelope message
verbatim; iOS maps status codes to its own sentences. Each is internally
consistent and iOS is the more human of the two. The one that matters: iOS
collapses 401 and 403 on login into "credentials did not match", but the server
returns 403 for *email verification required*, which is a different problem with
a different fix. *Cost: one case in `ThoughtPinsAuthFailure` — small, and worth
doing before email verification is ever switched on.*

**Consent copy differs by three edits.** Same meaning, same checkbox stem,
different body sentence and two bullets web has that iOS folds into a paragraph.
*Cost: pick one wording and use it in both. Editorial, but it is consent text,
so it should be one text.*

---

## Promises that are now scoped rather than universal

The published pages describe the product, not the iOS app. These sentences are
true of the web client and not of iOS, and the honest fix for most is editorial:

- support page: "manage devices" — web only
- terms: "search" — web only on iOS today
- privacy: "delete specific content" — web only
- AI disclosure: routing "can be corrected with undo" — web only

`REVIEW_NOTES.md` was corrected this pass where it overstated: the safety report
does not email support, and the iOS export is account JSON rather than a
Markdown vault.

**Recommendation:** before submitting, scope those four sentences on the
published pages to name the web app, or ship the iOS features. Scoping is an
afternoon; the features are not. The listing is the iOS listing, and a reviewer
who opens the support page from inside the app — which they can, it is linked in
Account — is one tap from a sentence the app does not honour.
