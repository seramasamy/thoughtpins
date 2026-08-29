# App Store Connect metadata — Thought Pins 1.0.0

The single source for the App Store Connect listing fields. Paste from here.
Where a field needs an owner decision, it says so; everything else is grounded
in what the app actually does at this SHA.

Written 2026-08-29. Copy that names a feature was checked against the code —
in particular it does **not** say "when you last spoke" (the People card shows
*Last mentioned*, which is when you last wrote about someone) and it does
**not** promise an Obsidian vault export on iOS (that is web-only; iOS exports
JSON).

---

## Identity

| Field | Value |
|---|---|
| App name | Thought Pins |
| Subtitle (30 char max) | A private memory for your life |
| Bundle ID | `com.thoughtpins.app` |
| SKU | `thoughtpins-ios-001` |
| Primary language | English (U.S.) |
| Primary category | Productivity |
| Secondary category | Lifestyle |
| Version | 1.0.0 |
| Copyright | 2026 Thought Pins |

**ASC version record:** create the version as **1.0.0**, not "1.0", so it
matches `MARKETING_VERSION` in `project.yml` before you attach a build.

## URLs

| Field | Value |
|---|---|
| Support URL | `https://thoughtpins.com/support` |
| Marketing URL | `https://thoughtpins.com` |
| Privacy Policy URL | `https://thoughtpins.com/privacy` |

## Promotional text (170 char max, editable without review)

> Write or speak a note and Thought Pins keeps it — then helps you find the
> people, places, and ideas in it when they matter again. Private by default.

## Description

> Thought Pins is a private place to keep what matters and find it again.
>
> Write a note, speak one, or import a link or file. Thought Pins reads what you
> keep and organizes it into the people, places, and ideas it touches, so your
> own words come back to you when they are useful — not buried in a list.
>
> Ask in plain language. The assistant answers only from what you have written,
> and tells you when it is drawing on your own journal rather than the world.
>
> • Capture by writing or voice, or import articles and documents
> • People, places, and source cards built from your own entries
> • A recap of your day, week, or month
> • Ask questions and get answers grounded in your notes
> • Export everything and delete anything — your data is yours
>
> Private by design. Nothing you write is shared: there is no feed, no
> profiles, and no other account can see your content. What you send the
> assistant is processed by a third-party AI provider you consent to, and
> nothing more.
>
> Thought Pins is free.

*Owner sign-off needed on the description wording before submission.*

## Keywords (100 char max, comma-separated, no spaces)

> journal,notes,memory,diary,voice notes,private,ai,recap,people,places,reminders,second brain

## What's New (first release)

> The first release of Thought Pins.

## App Review Information

| Field | Value |
|---|---|
| Sign-in required | Yes |
| Demo username | `review@thoughtpins.com` |
| Demo password | **In App Store Connect → App Review Information → Sign-In Information only. Not in this repository.** |
| Contact first/last name | *Owner* |
| Contact phone | *Owner* |
| Contact email | *Owner* |
| Notes | Paste the block between the ✂️ markers in `REVIEW_NOTES.md` |

## Content rights

Does your app contain, show, or access third-party content? **Yes** — the app
can fetch and display an article from a URL the person saves, for their own
reference. It does not redistribute that content to other users. Rationale for
the reviewer is in `REVIEW_NOTES.md`.

## Age rating

Complete the questionnaire from `apple-submission/AGE_RATING.md` — expect the
mature tier (17+/18+). Do not answer 4+/9+/12+.

## App Privacy

Answer from `apple-submission/APP_PRIVACY.md`, which matches
`PrivacyInfo.xcprivacy`: Email, Phone, User ID, Other User Content, Audio,
Photos or Videos — all Linked to You, all App Functionality, none for tracking.
No Diagnostics collected by the app (Sentry is backend-only and receives no
user content — see the Sentry decision note in `SUBMISSION_STATUS.md`).

## Export compliance

`ITSAppUsesNonExemptEncryption` is `false` in the built Info.plist. Answer
**No** to non-exempt encryption. Detail in `apple-submission/EXPORT_COMPLIANCE.md`.

## Accessibility Nutrition Labels

Declare only what `DEVICE_TEST_SCRIPT.md` verifies on the iOS-26 SDK build on
device. Do not pre-declare VoiceOver / Dynamic Type / sufficient contrast
support until that run confirms each; an unverified accessibility claim is a
rejection risk of its own.

## Pricing and availability

| Field | Value |
|---|---|
| Price | Free |
| In-app purchases | None |
| Availability | All territories **except the EU** |

**EU:** the operator is declaring **non-trader**, so EU distribution is off.
App Store Connect defaults to all 27 EU storefronts selected — actively
**deselect all of them** in Pricing and Availability, and set Business →
non-trader. This is deliberate; see the project's non-trader decision.
