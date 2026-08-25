# App Privacy answers — Thought Pins

What to enter in **App Store Connect → App Privacy**, and why each answer is
what it is. Every line was checked against what the shipped iOS target actually
transmits, not against what the product intends.

The binding artefacts are `mobile/ios/ThoughtPinsNative/Resources/PrivacyInfo.xcprivacy`
and `site/privacy.html`. All three must agree. If you change one, change all
three in the same commit — App Review compares the app's claims to the linked
policy, and a mismatch is worse than either statement alone.

---

## The short answers

- **Data used to track you:** none. `NSPrivacyTracking` is `false`,
  `NSPrivacyTrackingDomains` is empty, and there is no IDFA, no App Tracking
  Transparency prompt, no analytics SDK and no advertising SDK in the app.
- **Data linked to you:** the six types below. All of them are linked, because
  the whole product is an account holding one person's own material.
- **Data not linked to you:** none.

## Collect / Linked / Tracking, type by type

| App Store Connect type | Collected | Linked | Tracking | Purpose | Why |
|---|---|---|---|---|---|
| Contact Info → Email Address | Yes | Yes | No | App Functionality | Registration and sign-in (`/v1/auth/register`, `/v1/auth/login`) |
| Contact Info → Phone Number | Yes | Yes | No | App Functionality | Optional alternative identifier on the same endpoints |
| Identifiers → User ID | Yes | Yes | No | App Functionality | The account id returned by `/v1/me`, held in the session |
| User Content → Audio Data | Yes | Yes | No | App Functionality | Voice notes. `finishVoiceRecording` sends the recording to `uploadVoiceNote` |
| User Content → Photos or Videos | Yes | Yes | No | App Functionality | The file importer accepts `.image`; the upload provider reads the chosen file's bytes and base64-encodes them |
| User Content → Other User Content | Yes | Yes | No | App Functionality | Journal entries, chat messages, saved readings, imported documents |

## Deliberately answered "No"

| Type | Why not |
|---|---|
| Identifiers → Device ID | **Nothing in the app collects one.** There is no push entitlement, no `registerForRemoteNotifications`, and no call to `registerDevice` anywhere outside a unit test. `DeviceRegistration` exists in the API client and is unused by iOS. This was previously declared and has been removed; a gate now fails if the declaration and the code disagree in either direction. |
| Location | No location API is used, and there is no usage-description key for one |
| Contacts | Not used |
| Health & Fitness, Financial Info | Not used |
| Browsing History | Not used. Saving a link stores the article, not a history of pages visited |
| Search History | Chat text is stored as chat messages, which is User Content. There is no separate search-history surface |
| Usage Data / Product Interaction | No analytics SDK, no event pipeline |
| Diagnostics | No crash-reporting SDK in the app. Sentry is a backend dependency and is not in the iOS binary |
| Purchases | None. Free app, no IAP, no subscriptions |
| Sensitive Info | A judgement call worth recording. Apple's "Sensitive Info" means data the app *requires or is designed around* — racial or ethnic data, sexual orientation, pregnancy, disability, religious or political belief, trade-union membership, biometric or genetic data. A free-text journal can contain anything a person chooses to write, but the app neither asks for nor derives any of those categories, and declaring it would imply the product is built around them. Declared as User Content instead. If a feature is ever added that classifies entries into any of those categories, this answer changes. |

## Third parties

Content a person saves or asks about is sent to a third-party AI provider over
HTTPS for classification, extraction and replies. That provider acts as a
processor: it receives the content to perform the service and the content is
not sold, and is not used for advertising.

App Store Connect does not have a separate "shared with third party" toggle in
App Privacy — the collection itself is what gets declared, and it is, under
User Content. The provider relationship is disclosed to the person before any
content is sent: a consent screen that must be accepted, and
`https://thoughtpins.com/ai-disclosure`.

## Permissions the app requests

| Permission | Key | When |
|---|---|---|
| Microphone | `NSMicrophoneUsageDescription` | Only when the record button in Chat is tapped |

Nothing else. No location, contacts, photos, camera, calendars, or
notifications prompt. Files are chosen through the document picker, which runs
out of process and needs no usage description.

## Required-reason APIs (`NSPrivacyAccessedAPITypes`)

Declared: `NSPrivacyAccessedAPICategoryUserDefaults`, reason **CA92.1** — the
app reads and writes only its own defaults, through one `@AppStorage` key
recording that the voice-note disclosure was shown.

Checked and **not** used, so correctly absent: file timestamp APIs, system boot
time, disk space, and active keyboard. The upload provider calls
`resourceValues(forKeys:)` with `.fileSizeKey`, `.contentTypeKey` and
`.localizedNameKey`; none of those is on any required-reason list —
`.fileSizeKey` is the size of a file the person chose, not free disk space.
`scripts/check_ios_submission_source.py` ties this to the Swift so the manifest
cannot drift from the code.

## Entitlements

`mobile/ios/ThoughtPinsNative/Resources/ThoughtPins.entitlements` declares
exactly one: `com.apple.developer.applesignin` = `Default`.

That is correct and required — the app builds `SignInWithAppleButton` and
handles the credential. It is currently inert at runtime because production
reports `oauth_apple_enabled: false`; see `REVIEW_NOTES.md` for why that also
means no Google button is offered.

No other entitlement is declared, and none is needed: no push, no App Groups,
no Keychain sharing, no associated domains, no background modes.
