# Thought Pins Public Site

This directory is the static public site for `thoughtpins.com`. It contains the
product homepage, shared brand assets, and store-facing trust resources.

The app itself lives at `thoughtpins.com/app`. The public site owns legal,
support, security, account deletion, and AI disclosure URLs used for web launch,
TestFlight, App Store review, and Play Store review. The homepage detects a local
no-auth environment through `/v1/client-config` and labels its direct test-session
entry. Public production links always target the authenticated app.

Before public launch, have the policy and terms language reviewed, then keep
this directory aligned with the URLs configured in `.env.production.example`.
The backend public router also serves these same files from the API/app runtime image when `site/` is packaged. Keep file names stable because App Store, Play Store, client config, and smoke tests reference `/privacy`, `/terms`, `/support`, `/account/delete`, and `/ai-disclosure` directly.

The modern homepage and `/classic/` share `assets/product-showcase.css` and
the accessible device tabs in `assets/site.js`. Product images are captures of
the web app with fictional fixtures. Classic-only typography and surfaces live
in `assets/classic-site.css`; keep modern homepage refinements separate.

Run `cd frontend && npm run smoke:site:ui` for Chromium and WebKit coverage at
eight phone, tablet, and desktop widths, including device-tab keyboard use,
resizing, no-JavaScript fallback, dark appearance, contrast, and overflow. The
command starts a loopback static server that supports the production policy
URLs. No account or model-provider credentials are needed.
