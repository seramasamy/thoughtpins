# Thought Pins Public Site

This directory is the static public site for `thoughtpins.com`. It contains the
product homepage, shared brand assets, and store-facing trust resources.

The app itself lives at `app.thoughtpins.com/app`. The public site owns legal,
support, security, account deletion, and AI disclosure URLs used for web launch,
TestFlight, App Store review, and Play Store review. The homepage detects a local
no-auth environment through `/v1/client-config` and labels its direct test-session
entry. Public production links always target the authenticated app.

Before public launch, have the policy and terms language reviewed, then keep
this directory aligned with the URLs configured in `.env.production.example`.
The backend public router also serves these same files from the API/app runtime image when `site/` is packaged. Keep file names stable because App Store, Play Store, client config, and smoke tests reference `/privacy`, `/terms`, `/support`, `/account/delete`, and `/ai-disclosure` directly.
