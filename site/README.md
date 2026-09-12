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

The modern homepage follows **How it works → The app → Your control**. The
existing `#week` anchor now opens a directly scrollable set of examples; it is
kept for existing links. `/classic/` remains available with its **Modern Site**
return link. The modern header and footer do not advertise the classic route.

`assets/modern-home.css` owns this composition. `assets/labs.js` owns the
progressive reveals and example controls; `assets/motion-preference.js` shares
the session choice with the classic site;
`assets/constellation.js` owns the decorative canvas. Keep the network bounded
(64 nodes on phones, 112 otherwise, 30 draws/second, pixel ratio capped at 2).
Seeded floating nodes, warm glows and traveling signals retain the original
connected-memory character. A spanning tree and nearby links are computed only
on resize; the network stays connected without sorting neighbors every frame.
Pause when offscreen, hidden or leaving the page, and resume on restoration.
The motion toggle and live system Reduce Motion changes cover both canvas and
marquee. All content and native scrolling remain usable without JavaScript.
Product captures reserve their dimensions before lazy loading to avoid layout
shifts. `frontend/site-e2e/motion.spec.ts` covers these behavior boundaries.

Public diagrams in the repository use the self-contained static
[retrieval SVG](../docs/architecture/assets/retrieval-pipeline.svg), with a text
equivalent beside each use. Do not require GitHub's Mermaid runtime to read the
architecture. The SVG contains no scripts, external fonts or remote assets.
