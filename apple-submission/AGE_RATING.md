# Age rating — Thought Pins

**Decision: rate for the mature tier (17+ on the legacy scale, 18+ on the
2025 scale). Do not rate this 4+.**

Getting this wrong does not merely delay approval — Apple removes apps whose
rating understates what they can produce, after they are live. This file records
the reasoning so the answer can be defended or revisited, rather than re-guessed.

---

## Why not 4+, which is what a journal app looks like

Everything except the assistant would justify 4+: no social surface, no ads, no
purchases, no gambling, no user-to-user contact, no web browser.

The assistant is the whole of the argument. `POST /v1/chat` sends the person's
text to a third-party model and returns generated prose. Three things follow:

1. **The output is not enumerable.** We cannot list what it may say, which is
   the question an age rating actually asks.
2. **There is no output moderation of our own.** A search of `src/thoughtpins/`
   finds no moderation, refusal or category-filter layer between the model and
   the reply. We rely entirely on the provider's own safety behaviour, which we
   do not control and which can change without us shipping anything.
3. **Its grounding is the person's own journal**, which may contain anything
   they chose to write — including material about health, grief, sex,
   substances, or self-harm. The system prompt binds the model to that content
   (`memory_answer.py`: "NEVER claim external truth. Say 'your journal shows'"),
   so the more faithful it is, the more directly it can restate mature material.

Point 3 cuts against a low rating harder than an open-domain chatbot would, not
less: an assistant that faithfully recounts a difficult journal entry is doing
its job.

## Why not something in between

9+ and 13+ exist for infrequent or mild instances of enumerated categories.
Neither describes "can generate arbitrary text with no ceiling we impose." The
tier is not chosen because the app is lurid — it is chosen because the honest
answer to "how intense can this get?" is "we do not bound it."

## What this costs, stated plainly

A mature rating narrows the audience and affects discoverability, and it is the
wrong call for a journalling app in every respect except the one that matters.
It is still the right call: the alternative failure mode is removal after
launch, with the rating cited.

**If we want a lower rating later, it has to be earned, not re-answered.** The
route is a moderation layer we control between the model and the reply, with
categories we can name and test. Then the questionnaire can be answered from
what the app permits rather than from what a third party might emit.

## Draft App Store Connect answers

App Store Connect's rating questionnaire changed in 2025 and the exact wording
of the AI questions differs from the legacy form. **Confirm each against the
live form** — these are the intended answers, not a transcription.

| Question | Answer | Why |
|---|---|---|
| Does the app include AI chatbot or generative AI features? | **Yes** | `/v1/chat` returns model-generated prose |
| Can that AI generate unrestricted or unfiltered content? | **Yes** | No moderation layer of our own; provider safety only |
| Cartoon or Fantasy Violence | None | Nothing in the app depicts any |
| Realistic Violence | None | " |
| Sexual Content or Nudity | **None as app content**; possible in generated text | The app ships none. This is why the AI answers above carry the rating |
| Profanity or Crude Humor | Same | The model may restate what the person wrote |
| Alcohol, Tobacco, or Drug Use | Same | " |
| Horror/Fear Themes | Same | " |
| Medical/Treatment Information | **None** | The app offers no medical feature and gives no advice; it can recount health notes the person wrote, which is journal content, not medical information as a feature |
| Gambling, Contests | None | Neither exists |
| Unrestricted Web Access | **No** | There is no in-app browser. "Open original" hands a URL the person saved to the system browser, and article import fetches a URL they typed. Neither is a browsing surface |
| User Generated Content | **No** | Nothing is shared. There is no feed, no profiles, no following, no comments, no links out, and no way for one account to see another's content |
| Made for Kids | **No** | Never enable this |

### The July 9, 2026 social-capability questions

Apple added these after the AI questions. For this app every answer is the
negative one, and each is grounded in the code, not memory.

| Question | Answer | Why |
|---|---|---|
| User-to-user communication (messaging, chat between users) | **None** | Chat is exclusively user-to-assistant (`chat/reply.py` calls the model). There are no messaging endpoints in `api_routes/` and no route by which one account can send anything to another |
| User-generated content shared with or visible to other users | **None** | Every entry, reply, and card is tenant-scoped; no endpoint exposes another account's content |
| Social networking features (profiles, following, discovery) | **None** | No profiles, no follow graph, no discovery surface exist in the code |
| Can users contact each other? | **No** | Same as above; there is no inter-account surface at all |

Two things to disclose in the rationale so they are not mistaken for social
features: the app presents the OS **share sheet** (`ThoughtPinsShareSheet`,
used at the account-export step) — that hands a file to the person's own other
apps, not to another Thought Pins user — and **invite redemption**
(`redeemInvite`) gates access during the closed beta; a code admits the account
that enters it and connects it to no one.

### Parental controls and frequency

| Question | Answer | Why |
|---|---|---|
| Does the app offer parental controls / age gates within the app? | **No** | The 17+/18+ store rating is the gate; there is no in-app control |
| Frequency of the mature content that drives the rating | **Infrequent/Mild** is defensible, but choose **Frequent/Intense** if unsure | The app ships no mature content of its own; the exposure is entirely what an unfiltered model *could* generate from what the person writes. Rate to the capability, not the expectation |

### Korea (KMRB/GRAC) rating override, added 2026-08-12

Apple now asks for a Korea-specific rating. With unrestricted AI generation and
no in-app moderation, the honest Korea answer matches the mature tier — do
**not** self-assign a lower Korea rating than the overall one. If Apple's Korea
questionnaire asks specifically about AI-generated content, answer that it is
present and unfiltered, consistent with the AI questions above.

## The UGC answer is the one most likely to be challenged

Answer **No**, and be ready to explain why in the review notes: Apple's UGC
questions exist because content moves between people. Here nothing does. Every
entry, reply and card is visible only to the account that made it.

What we do have anyway, and should say so: an in-app report action on any chat
reply (Chat → "Report this reply"), which posts to `/v1/safety/reports` and is
answered at support@thoughtpins.com.

## Confirmed against the submission build (2026-08-29)

Re-checked mechanically rather than from memory, because every reason below is
a claim about what the code does:

| Premise | How it was checked | Result |
|---|---|---|
| Still no moderation layer of our own | searched `src/thoughtpins/` for moderation, refusal, and filter layers | none; the only hit is the word "moderate" as a style value in `chat/personality.py` |
| The assistant still returns model prose | `/v1/chat` unchanged | holds |
| In-app reporting exists, as this file claims | Chat > "Report this reply" > `reportChatReply` > `POST /v1/safety/reports` | wired and exercised against production |
| No in-app browser | searched for `WKWebView` and `SFSafariViewController` | neither is present anywhere in the iOS source |
| No account-to-account surface | searched for follow, feed, comment, and every share path | no inter-account surface. The one on-screen "share" is the OS share sheet (`ThoughtPinsShareSheet`) used to export the account's own data to the person's other apps — it moves nothing between accounts |

**The decision stands: mature tier.** Nothing changed that would justify a
lower one, and the route to a lower one is unchanged and stated below: a
moderation layer we own and can test, not a re-answered questionnaire.

## Revisit this when

- A moderation layer of our own lands, which is the only thing that could
  justify a lower tier.
- Sharing, export-to-others, or any account-to-account surface is added, which
  would flip the UGC answer to Yes and bring 1.2's full set of obligations.
- Apple changes the questionnaire again.
