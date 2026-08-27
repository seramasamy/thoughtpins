"""Stop third-party libraries logging content we promised not to log.

`AGENTS.md` forbids logging raw journal text, source text, tokens and
authorization headers, and the privacy policy depends on that holding. Our own
code obeys it. The model provider's SDK does not: at DEBUG, `openai`'s base
client logs its full request options, and for this service that payload is the
prompt -- which is the person's journal entry, verbatim. A driven request with a
distinctive sentinel in the entry text found it in nine log lines.

Nothing prevented that in production. `LOG_LEVEL` defaults to INFO, so it is off
by default, but it is one environment variable away from being on, and the
moment someone reaches for DEBUG is an incident at 11pm -- exactly when nobody
is thinking about what the provider SDK writes to stdout.

So the level of these loggers is not ours to hand out. Whatever `LOG_LEVEL`
says, the libraries that echo request bodies are pinned at INFO or above. Our
own loggers are untouched, so raising `LOG_LEVEL` still does what it is for.
"""

from __future__ import annotations

import logging

# Libraries that write request or response payloads at DEBUG.
#
# openai/anthropic: the prompt, which is journal text.
# httpcore/urllib3: raw headers, which carry the provider credential.
# httpx: only logs method and URL, but its transport chatter is noise at DEBUG
# and it is the layer the provider SDKs sit on, so it is pinned with them.
PAYLOAD_LOGGERS = (
    "openai",
    "openai._base_client",
    "anthropic",
    "anthropic._base_client",
    "httpx",
    "httpx2",
    "httpcore",
    "urllib3",
    "urllib3.connectionpool",
)

FLOOR = logging.INFO


def apply_logging_policy() -> None:
    """Pin the payload-logging libraries at INFO or above. Idempotent."""
    for name in PAYLOAD_LOGGERS:
        logger = logging.getLogger(name)
        if logger.level == logging.NOTSET or logger.level < FLOOR:
            logger.setLevel(FLOOR)
