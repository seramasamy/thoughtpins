# Source Layout

One installable package, `src/thoughtpins`. The full module map with size
ratchets is [`ARCHITECTURE_MODULES.md`](../ARCHITECTURE_MODULES.md); this is the
shape at a glance.

| Package | Holds |
| --- | --- |
| `api_routes/`, `api_contracts/` | HTTP surface and the request/response types it is pinned to |
| `chat/` | The engine every client talks to: routing, reply generation, actions, personality, style, conversation state |
| `memory/` | Retrieval, ranking, context assembly, the graph backend, provenance and safety |
| `ingestion/` | Turning a message into structured memory: classification, extraction, jobs |
| `bot/` | Telegram adapter — a transport, not a place for product behaviour |
| `llm/` | Provider-agnostic client against any OpenAI-compatible endpoint |
| `vault/`, `obsidian/` | Export and import of a plain Markdown vault |
| `media/`, `reports/`, `demo/`, `founder/` | Attachments, recaps, seeded demo data, local operator diagnostics |

## The rule that shapes this

Core layers may not import a transport. `scripts/check_architecture_budget.py`
enforces it and files a numbered exception for anything that still does — there
is currently one, a diagnostics call, and it carries its reason.

That rule earned its keep. `chat/engine.py` once imported reply generation from
`bot/commands.py`, so every web and native answer was produced by a function
living in the Telegram module. Five of the six names it reached for were
re-exports of things already in core; the sixth was wrapped to apply Telegram's
3,900-character message limit, which meant **report answers served to the web
were being truncated at a Telegram boundary**. A dependency-direction gate can
see that core imports a transport. It cannot see that the transport changed the
answer on the way through — that took reading the code.

Legacy modules carry size ratchets: they may shrink, never grow. When one blocks
a change, extract something. When nothing is extractable — because a test seam
pins it by name, for instance — raise the budget and record why in the
[technical debt register](../docs/architecture/TECHNICAL_DEBT_REGISTER.md). The
number is a prompt to look, not a target to satisfy.
