# Sign in with Apple

The native and web clients submit Apple's identity token, a one-time
authorization code, and a nonce to the shared OAuth endpoint. The server checks
signature, issuer, audience and nonce, exchanges the code, stores the refresh
credential encrypted, and revokes it before completing account deletion.
State mismatch and incomplete credentials stop before account creation.

Native support is already in `ThoughtPinsAuthentication.swift` and
`ThoughtPinsAuthView.swift`, using Apple's AuthenticationServices button. The
native target has `com.apple.developer.applesignin = Default`; the developer
portal App ID and the signed provisioning profile must allow that entitlement.
The bundle identifier is `com.thoughtpins.app`.

## Account configuration

A `.p8` file alone does not identify its permitted services. A Sign in with
Apple key and an App Store Connect API key serve different purposes. The latter
also needs its Issuer ID for team API requests and cannot substitute for a
Sign in with Apple key. Keep either key out of source control, logs and chat.

| Setting | Purpose |
| --- | --- |
| `APPLE_OAUTH_CLIENT_IDS` | Allowed token audiences. Include `com.thoughtpins.app` for native and the actual registered Services ID for web. |
| `APPLE_OAUTH_TEAM_ID` | Developer Team ID owning the App ID and Sign in with Apple key. |
| `APPLE_OAUTH_KEY_ID` | Identifier of that Sign in with Apple key. |
| `APPLE_OAUTH_PRIVATE_KEY` or `APPLE_OAUTH_PRIVATE_KEY_PATH` | Private PEM material in deployment secrets, or a protected mounted file. |
| `APPLE_OAUTH_WEB_CLIENT_ID` | The explicit web Services ID, independent of audience ordering. Leave empty for native-only support. `VITE_APPLE_CLIENT_ID` remains a compatibility fallback. |
| `APPLE_OAUTH_REDIRECT_URIS` | Exact public HTTPS return URLs. For the production web app, register `https://thoughtpins.com/app/`, including the trailing slash. |

Enable Sign in with Apple on the primary App ID. For web, create a Services ID,
associate it with that primary App ID, and register `thoughtpins.com` and the
exact return URL. Register any additional hostname only if it actually serves
the app and is tested. Marketing and classic-site account links lead to `/app/`,
which owns the sign-in flow; they do not need a second implementation.

The web button stays hidden for a native-only configuration. Runtime public
client IDs take precedence over Vite build defaults; an iOS bundle identifier
is never inferred to be a web Services ID. Production validation requires an
allowed web audience and HTTPS return URLs when web sign-in is configured.
SDK preload on the login screen reduces popup-opening delays. A blocked or
failed SDK download can be retried without reloading the app.

Configure Apple's private email relay for the sender/domain used by Resend
before relying on emailed sign-in links for Hide My Email addresses. Regenerate
and verify the native distribution profile after enabling capabilities.

## What counts as verification

Automated coverage includes real JWT signature/nonce checks with generated
keys, code-exchange/revocation HTTP doubles, encrypted credentials, account
linking and deletion failure, native request payloads, and browser success,
state mismatch, incomplete code, SDK download failure and native-only gating.
Mock Apple responses do not prove live Apple account authorization.

A request using an invented authorization code is also not proof: Apple's
`invalid_grant` can be returned even with a deliberately wrong signing key.
Do not turn on the provider based on that response alone.

Before offering Apple sign-in to customers:

1. Verify the key's service and primary App ID in the developer portal.
2. Run the signed release on a physical iPhone and iPad. Exercise first sign-in
   with Share My Email and Hide My Email, cancellation and subsequent sign-in
   without Apple's first-login name payload.
3. On web, repeat in Safari, Chromium and Firefox at the registered HTTPS URL.
4. Confirm renewal, explicit linking to an existing password account, export,
   and account deletion with Apple revocation. Test temporary revocation failure
   and retry without falsely reporting deletion.
5. Confirm Apple access is revoked, then create a fresh account if appropriate.
   Do not delete the standing App Review demo account during this check.

The separate distribution-signing and App Store Connect requirements remain in
[Submission status](SUBMISSION_STATUS.md). Adding a sign-in key does not grant
permission to upload a signed app or edit its App Store metadata.

Primary references: [web configuration](https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web),
[Sign in with Apple keys](https://developer.apple.com/help/account/capabilities/create-a-sign-in-with-apple-private-key),
[private email relay](https://developer.apple.com/help/account/capabilities/configure-private-email-relay-service),
[account deletion and token revocation](https://developer.apple.com/documentation/technotes/tn3194-handling-account-deletions-and-revoking-tokens-for-sign-in-with-apple),
and [App Store Connect API](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api).
