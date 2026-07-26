# Founder Local Mode

This directory is the local/private operations area for Thought Pins founder
testing. It is safe to keep this directory in a public repository as long as
`founder/private/` stays ignored and no secrets or personal memory exports are
added here.

Use founder mode only for local Telegram testing:

- `ENABLE_TELEGRAM_BOT=true`
- `TELEGRAM_TEST_MODE=true`
- `ENABLE_FOUNDER_MODE=true`
- `FOUNDER_ACCESS_CODE=<local-code>`
- `CONFIDENTIAL_ACCESS_CODE=<local-private-code>`

Founder mode is blocked by production startup validation. Public app clients
should use `/v1/chat`, `/v1/entries`, `/v1/library`, account export/delete, and
JWT/OAuth auth flows instead.

See [TELEGRAM_RUNBOOK.md](TELEGRAM_RUNBOOK.md) for the operational command list,
health checks, memory-aware chat behavior, backup/restore flow, and local reset
commands.
