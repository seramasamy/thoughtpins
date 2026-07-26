# Thought Pins Domain and DNS

`thoughtpins.com` is the production identity for the product. Keep public
website, app, API, and staging names separate so mobile clients and store review
metadata never depend on founder-local infrastructure.

## Hostnames

- `thoughtpins.com`: public site, legal pages, support, account deletion, AI
  disclosure.
- `www.thoughtpins.com`: redirect to `thoughtpins.com`.
- `app.thoughtpins.com`: production web app served by the backend at `/app`.
- `api.thoughtpins.com`: production `/v1` API.
- `staging.thoughtpins.com`: staging web app.
- `api-staging.thoughtpins.com`: staging `/v1` API.

Optional later:

- `status.thoughtpins.com`: public uptime/status page.
- `docs.thoughtpins.com`: API/product docs if the public docs outgrow the main
  site.

## DNS Records

Create these after choosing the host:

| Name | Type | Target |
| --- | --- | --- |
| `@` | `A` or `CNAME/ALIAS` | public site host |
| `www` | `CNAME` | `thoughtpins.com` or public site host |
| `app` | `CNAME` | app/API host |
| `api` | `CNAME` | app/API host |
| `staging` | `CNAME` | staging host |
| `api-staging` | `CNAME` | staging host |

Use provider-managed TLS. Do not run production without HTTPS on every public
hostname.

Configure email separately before publishing `support@thoughtpins.com` as the
support channel. The app and public pages assume that mailbox exists.

## Routing

The recommended first production layout is:

- Static public site from `site/` at `thoughtpins.com`.
- Backend API/web process at `app.thoughtpins.com` and `api.thoughtpins.com`.
- `/app` is the web client path.
- `/v1/*` is the versioned API path.
- `/privacy`, `/terms`, `/support`, `/account/delete`, and `/ai-disclosure`
  exist both as static public pages and backend fallback pages.

`deploy/Caddyfile.thoughtpins.example` shows a simple reverse-proxy shape for a
single VM. Managed platforms such as Fly.io, Railway, Render, or Vercel/Netlify
will express the same mapping in their dashboard or config files.

## Production Environment

Use these public URL values:

```env
PRIVACY_POLICY_URL=https://thoughtpins.com/privacy
TERMS_URL=https://thoughtpins.com/terms
SUPPORT_URL=https://thoughtpins.com/support
ACCOUNT_DELETION_URL=https://thoughtpins.com/account/delete
AI_DISCLOSURE_URL=https://thoughtpins.com/ai-disclosure
WEB_APP_URL=https://app.thoughtpins.com/app
CORS_ALLOW_ORIGINS=https://app.thoughtpins.com
ANDROID_STORE_URL=https://play.google.com/store/apps/details?id=com.thoughtpins.app
```

Run before deploy. These checks keep `.env.production.example`, `deploy/closed-beta-deployment-packet.json`, store URLs, and domain docs aligned:

```powershell
$env:PYTHONPATH="src"
python scripts/check_deployment_packet.py
python scripts/check_domain_readiness.py
python scripts/release_check.py
```

Run after DNS and TLS are live:

```powershell
.\scripts\run_staging_smoke.ps1
```

## Store Review Dependency

Apple and Google review should see:

- Public privacy policy.
- Public support page or support email.
- Public account deletion instructions.
- Public AI disclosure.
- In-app account deletion path.
- Review/test credentials.

Do not submit native apps until these pages are live over HTTPS.
