# Where Thought Pins fits

Reviewed 11 September 2026. This is a selected landscape of 13 tools across
general assistants, Obsidian workflows, research, notes, memory infrastructure,
and agents. It is not an exhaustive internet directory or a hands-on benchmark.
Product descriptions below come from their maintainers; the fit assessment is
our interpretation of those descriptions and Thought Pins' implementation.

| Tool | What its documentation establishes |
| --- | --- |
| [ChatGPT](https://learn.chatgpt.com/docs/customization/memories) | Carries useful context across chats, with memory controls. It should not be described as stateless. |
| [Claude](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context) | Offers chat search and editable memory; availability and scope depend on the feature, plan, and workspace settings. |
| [Claudian](https://github.com/YishenTu/claudian) | Embeds Claude Code and other coding agents in an Obsidian vault, with file reading, editing, search, and multi-step work. This is a community plugin. |
| [Copilot for Obsidian](https://www.obsidiancopilot.com/en) | Provides agent workflows, semantic search and related notes within Obsidian, with multiple model options. |
| [Gemini Notebook](https://workspace.google.com/products/gemini-notebook/) | Google's source-based research product, formerly NotebookLM; answers can cite uploaded sources for inspection. |
| [Mem](https://help.mem.ai/features/search) | Combines quick lookup, search across notes, and AI-assisted retrieval when exact wording is unknown. |
| [Reflect](https://reflect.app/) | Offers backlinked notes, AI assistance, calendar integration, and mobile capture. Its documentation also describes encryption; privacy is not an exclusive Thought Pins feature. |
| [Tana Outliner](https://outliner.tana.inc/) | Uses nodes, supertags, fields, search, and AI to build structured knowledge. It is distinct from the company's meeting product at tana.inc. |
| [Khoj](https://docs.khoj.dev/) | An open-source personal AI with file search, chat, web access, Obsidian integration, and self-hosting. It is a close alternative, including for people who want control of their deployment. |
| [Mem0](https://github.com/mem0ai/mem0) | Supplies user/session/agent memory through libraries, SDKs, a self-hosted server, and a managed platform. |
| [Zep](https://help.getzep.com/concepts) | Builds temporal context graphs from messages and other data and retrieves context for agents, including entities, relationships and changing facts. |
| [Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/) | Combines persistent profile/working memory, searchable session history, skills, and optional external memory providers. It is not limited to a short profile file. |
| [OpenClaw](https://docs.openclaw.ai/concepts/memory) | Provides persistent memory with file-backed records and configurable search as part of its agent environment. |

Thought Pins combines these steps in one workflow: capture a journal moment,
derive typed memories, revisit a person or place, inspect the source, and retain
control through account export and deletion. The
[module map](../../ARCHITECTURE_MODULES.md),
[retrieval walkthrough](RETRIEVAL_ARCHITECTURE.md), and
[vault contract](OBSIDIAN_INTEROPERABILITY.md) show how this is implemented.

The main differences here concern scope. General assistants cover broad tasks;
Obsidian agents work within an existing vault; research notebooks organize a
collection of sources. Mem0 and Zep provide infrastructure for other products,
while Hermes and OpenClaw include tool execution and automation. Thought Pins
centers its application on a personal record. These categories overlap, and
other tools can also support journaling or provenance.

No paid accounts or model calls were used for this comparison. We have not
established a retrieval-quality, privacy, reliability, latency, or cost advantage
over these products. Feature descriptions and names can change; follow the
linked documentation when choosing. Store distribution and production evidence
for Thought Pins remain subject to its
[validation limits](../../README.md#validation-and-limits).
