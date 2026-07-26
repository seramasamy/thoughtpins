# Support

## Product Help

Use the support page at `https://thoughtpins.com/support` for account, privacy,
export, deletion, and product-use questions once the hosted service is live.

For a self-hosted installation, first review `README.md`,
`docs/operations/PRODUCTION_RUNBOOK.md`, and the troubleshooting output from:

```text
python scripts/check_host_capabilities.py
python scripts/release_check.py --strict-quality
```

Public issue reports should contain a minimal reproduction, expected and actual
behavior, platform and version information, and privacy-safe logs. Remove access
tokens, email addresses, journal text, database contents, local paths, signing
material, and provider identifiers before posting.

## Security And Privacy

Do not use a public support channel for suspected vulnerabilities or accidental
data exposure. Follow `SECURITY.md` and use the repository host's private
vulnerability-reporting channel.

## Scope

The community project is provided under the terms in `LICENSE`. Maintainers may
prioritize regressions, data integrity, tenant isolation, security, portability,
and supported release configurations over environment-specific customization.
