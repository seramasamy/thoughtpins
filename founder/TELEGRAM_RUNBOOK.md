# Founder Telegram Runbook

This mode is for personal/founder use. Telegram is the client; the same backend
memory, ingestion, query, privacy, and export paths remain in use.

## Local Setup

Required local `.env` values:

```env
ENABLE_TELEGRAM_BOT=true
TELEGRAM_BOT_TOKEN=<telegram-bot-token>
TELEGRAM_TEST_MODE=true
ENABLE_FOUNDER_MODE=true
FOUNDER_ACCESS_CODE=<local-founder-code>
CONFIDENTIAL_ACCESS_CODE=<local-private-code>
LLM_API_KEY=<provider-api-key>
LLM_MODEL=<configured-chat-model>
MEMORY_CONTEXT_MODE=smart
```

Run API and Telegram separately while developing:

```powershell
.\scripts\run_local.ps1 -ApiOnly
.\scripts\run_local.ps1 -BotOnly
```

For solo founder use, SQLite plus local thread jobs are acceptable. For a hosted
always-on deployment, prefer PostgreSQL, Redis, and a worker process.

## Natural Requests

You do not need slash commands for normal founder use. Plain requests route to
the same tested command handlers when the intent is clear:

- `search my memory for Maya and the bar`
- `what did I write today`
- `show recent entries`
- `show saved articles`
- `show source <title or id>`
- `is everything running`
- `run a health check`

Destructive, private-data, or expensive operations require an explicit
confirmation reply before running: undo, forget, export, backup creation,
reindex, rename, merge, and confidential-mode unlock. Normal writing such as
`Recipe idea: ...`, `Date night note: ...`, `Networking event note: ...`, and
long journal essays still saves as journal memory.

## Daily Telegram Commands

- `/status`: library size, mode, jobs, latest backup, latest entry.
- `/doctor`: operational health for DB, LLM, worker, Redis, backups, disk, and
  Telegram mode.
- `/audit`: memory quality, graph/retrieval status, source-library health, and
  stale job audit.
- `/backup`: create a zip backup and send it through Telegram when small enough.
- `/backup list`: list recent local backup files.
- `/backup smoke`: create a backup, restore it into scratch space, verify the
  manifest and included roots, then remove the scratch restore.
- `/export`: export the Obsidian vault.
- `/export data`: send a JSON account export.
- `/jobs`: show ingestion job counts and recent errors.
- `/recent`: show recent entries.
- `/ask <question>`: ask over standard entries with the configured memory
  context mode.
- `/askfull <question>`: force the exhaustive context package for one audit
  question.
- `/context`: show the active context mode and prompt budget.
- `/context why <question>`: show section-level smart context diagnostics
  without printing memory text.
- `/people`, `/places`, `/concepts`: review the graph library from Telegram.
- `/rename <old> -> <new>`: rename an entity while keeping the old name as an
  alias.
- `/merge <keep> <duplicate>`: merge duplicate entities and move references.
- `/forget memory <id>`: delete a single extracted memory and its linked
  relationship rows.
- `/forget entity <name>`: delete an orphan entity only when it has no
  remaining references.
- `/read <url or pasted text>`: save an article/document into reading memory.
  URLs are fetched only through public or authorized source paths; otherwise
  paste text you have access to. If a URL is inaccessible, Thought Pins stores
  metadata-only source provenance and asks for pasted/uploaded text. If the same
  message includes a long pasted article, it is stored as user-provided content.
- `/library`: list saved articles and documents.
- `/source <id or title>`: inspect one saved source and first excerpts.
- `/memory`: compact memory health, recent memories, recent sources, and quick
  retrieval commands.
- `/memory search <query>`: search memory without switching mental modes.
- `/undo`: delete the most recent Telegram-saved entry, source, or correction
  from this chat. If the item was a correction, superseded memories are restored
  when possible.
- `/confidential on`: include private entries in answers after entering the
  configured confidential access code.
- `/founder on <code>`: enable the founder test personality.

## Memory-Aware Chat

Plain Telegram messages are not limited to canned replies. Conversation mode now
attaches a long-context memory package to each LLM response. The default mode is
`smart`:

- retained Telegram chat history for the current chat, bounded locally;
- the navigational memory map: people, places, events, clusters, relationships,
  and open action items;
- the full structured journal database when the library is still small enough;
- otherwise, query-relevant memories, recent memories, open reminders, relevant
  raw entry excerpts, recent expenses, and recent entries;
- saved article/document source summaries and excerpts when relevant;
- exported vault markdown text for the current user, when files exist;
- private entries only when `/confidential on` is active.

Plain Telegram text now uses the same durable chat engine as `/v1/chat`.
Normal chat turns, natural journal saves, document/article intent, corrections,
search/status/library requests, and natural undo confirmations are recorded in
`chat_conversations`, `chat_messages`, and `pending_chat_actions`. Explicit
slash commands still use the Telegram command handlers, and operational natural
requests such as backup/export/rename/merge/confidential unlock keep their
confirmation guardrails.

This is prompt context, not Telegram file upload. The bot reads database rows and
local vault markdown, renders them into text, and sends that text to the LLM with
the current message. The LLM is instructed to use the context naturally: mention
relevant past projects, people, events, reminders, and emotional continuity when
the user refers to them, without dumping the database.

Direct memory questions still work with `/ask <question>`, but normal chat can
also refer to the same memory library. For example, "I'm thinking about that
memory router again" should bring up the prior memory-router work and any related
open action items.

Corrections are active memory edits, not just notes. `/correct <text>` and
natural messages like "Actually Steve's kid is Geoff, not Jeff" create correction
memories, mark conflicting old extracted memories as superseded, and keep search
from treating those superseded memories as current facts.

Use `/askfull <question>` when you want to audit exact recall against the
exhaustive context package. Founder mode should normally stay on `smart` because
it matches the production product behavior and avoids making every casual chat
slow or noisy. The full path remains available for debugging, migration checks,
and "show me everything you know about X" investigations.

Founder/test Telegram chats are bound to a dedicated Telegram user even when the
system is locked. That prevents local app test accounts from being accidentally
used as the founder bot identity.

Pasted essays are kept as one journal entry up to the backend input limit of
50,000 characters. Longer messages are rejected with a clear Telegram reply so
they can be resent in smaller sections.

Telegram reminder delivery polls due action items and sends each due reminder
once. The interval is controlled by `TELEGRAM_REMINDER_POLL_SECONDS` and defaults
to 300 seconds.

## Verification

Current local gate:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe scripts\run_pytest.py tests\test_telegram_modes.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts\evaluate_memory_quality.py
.\.venv\Scripts\python.exe scripts\evaluate_llm_workflow.py
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe scripts\smoke_founder_local.py
.\.venv\Scripts\python.exe scripts\release_check.py --strict-quality
```

The Telegram test suite covers founder/test access, confidential mode, startup
validation, memory-aware conversation prompts, vault context, long chat history,
long essay routing, natural-language command routing, generated note examples,
expense context rendering, and locked-mode Telegram user isolation.

The live LLM workflow eval creates a disposable synthetic Telegram user,
ingests representative journal/reminder/expense/essay/social entries, asks and
chats over the stored memory, checks the result quality, and deletes its own
database rows, vault files, vector rows, and conversation cache.

Run maintenance after vector-store changes, large imports, or correction-heavy
sessions:

```powershell
.\.venv\Scripts\python.exe scripts\reindex_vectors.py --verify-query "recent work"
.\.venv\Scripts\python.exe scripts\memory_maintenance.py --reindex
```

For production-quality memory retrieval, use a real hosted embedding provider
while keeping the configured chat model:

```env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

Then run the reindex command above so old memories are embedded with the new
model.

Reset local memory before a fresh engineering/import pass:

```powershell
.\.venv\Scripts\python.exe scripts\clear_memory_data.py --dry-run
.\.venv\Scripts\python.exe scripts\clear_memory_data.py --yes
```

The reset command creates a backup by default, preserves users/auth
configuration, clears journal/library/graph/report rows, clears vault/report
files and conversation cache, and resets the derived vector index.

## Backup and Restore

Backups are written to `backups/` and include:

- `data/`
- `vault/`
- `reports/`
- `manifest.json`

Secrets are not included. Keep `.env` in a separate password manager.

Create a backup from Telegram:

```text
/backup
```

Run a restore smoke test from Telegram:

```text
/backup smoke
```

Restore a backup into a fresh inspection directory:

```powershell
python scripts/restore_backup.py backups\thoughtpins_backup_YYYY-MM-DD_HHMMSS_telegram.zip --target .tmp\restore-check
```

Run the same restore smoke test from the shell:

```powershell
python scripts/smoke_restore_backup.py
```

Inspect the extracted files before copying them into an active app directory.
Stop the API/bot before replacing active database or vault files.

## Hosted Founder Deployment

Minimum private deployment:

- One VPS or private VM.
- API process: `python -m thoughtpins.server --api-only`.
- Bot process: `python -m thoughtpins.server --bot-only`.
- Daily encrypted server snapshot.
- External uptime monitor hitting `/health`.
- Rotate Telegram and LLM keys before first hosted run.

Recommended private deployment:

- PostgreSQL.
- Redis.
- API process.
- Worker process: `python -m thoughtpins.worker`.
- Telegram bot process.
- Object storage or encrypted volume snapshots for backups.

## Recovery Checklist

1. Stop API, worker, and bot.
2. Restore backup into an inspection directory.
3. Copy required `data/`, `vault/`, and `reports/` files into the app root.
4. Restore `.env` from password manager.
5. Start API.
6. Run `/doctor`.
7. Start Telegram bot.
8. Send `/status`, `/recent`, and a small test journal entry.

## Platform Boundary

Keep Telegram founder mode local/private. Before exposing to other users, use
the App Store/Play Store path:

- PostgreSQL RLS verified with a non-owner app role.
- Redis-backed rate limiting.
- Celery worker.
- OAuth/client auth.
- Privacy policy and account deletion URL.
- Native clients against the `/v1` API contract.
