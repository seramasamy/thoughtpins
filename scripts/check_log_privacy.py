"""Fail on runtime log calls that expose identifiers or likely user content.

A static check of logger call sites. It catches identifier templates (email=,
phone=, tokens), content-named arguments -- directly, through slices, f-strings,
concatenation and pass-through wrappers -- and raw exception objects, whose
text can quote the input they failed on. It cannot see what a variable with a
neutral name holds at run time, so it narrows the risk rather than proving logs
content-free; the reviewed exceptions below are the ones judged safe.

The traceback logger.exception() attaches on its own is not a call-site
matter: thoughtpins.log_redaction withholds every logged exception's message
at the logging level, and logging_config routes the standard-library tree
(uvicorn, Celery, libraries) through it. tests/test_no_sensitive_data_in_logs.py
proves both.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGER_METHODS = {"trace", "debug", "info", "success", "warning", "error", "critical", "exception"}
SENSITIVE_TEMPLATE_PATTERNS = [
    re.compile(r"\bemail\s*=\s*\{\}"),
    re.compile(r"\bphone\s*=\s*\{\}"),
    re.compile(r"\btelegram\s*=\s*\{\}"),
    re.compile(r"\bchat(?:_id)?\s*=\s*\{\}"),
    re.compile(r"\bfor\s+chat\s+\{\}"),
    re.compile(r"\b(api[_-]?key|password|token)\s*=\s*\{\}"),
]
BOT_USER_ID_PATTERN = re.compile(r"\buser_id\s*=\s*\{\}")
EXCLUDED_DIRS = {"__pycache__"}

# Values that carry what someone wrote, or names drawn from it. Passing one to a
# logger puts journal content in hosted logs, which account deletion cannot
# reach. Production logged "Created new entity: <name>" this way until
# September 2026. Log a length, an identifier or a type instead.
CONTENT_ARGUMENT_NAMES = frozenset(
    {
        "alias",
        "answer",
        "body",
        "canonical_name",
        "caption",
        "content",
        "display_name",
        "entity_name",
        "excerpt",
        "message",
        "name",
        "note",
        "prompt",
        "query",
        "question",
        "raw_text",
        "snippet",
        "summary",
        "surface_name",
        "text",
        "title",
        "transcript",
    }
)
# Names conventionally bound to a caught exception. Logging one prints its
# message, which for SQLAlchemy includes statement parameters and for pydantic,
# JSON and provider errors the input that failed. Log type(exc).__name__.
EXCEPTION_ARGUMENT_NAMES = frozenset({"e", "err", "error", "ex", "exc", "ve"})
# Infrastructure failures whose message helps an operator and cannot carry user
# content, keyed by file and log template, each with its reason.
ALLOWED_EXCEPTION_LOGS = {
    ("src/thoughtpins/api_routes/auth.py", "Magic link delivery failed for {}: {}"): "email provider response",
    ("src/thoughtpins/bot/disclosure.py", "Could not load disclosure state: {}"): "local settings file read",
    (
        "src/thoughtpins/bot/reminders.py",
        "Could not load Telegram reminder sent log: {}",
    ): "local bookkeeping file read",
    ("src/thoughtpins/invite_requests.py", "Invite digest delivery failed: {}"): "email provider response",
    ("src/thoughtpins/logging_config.py", "Sentry initialization failed: {}"): "SDK configuration",
    ("src/thoughtpins/memory/graph_backend.py", "{} skipped inside existing event loop: {}"): "event-loop state",
    (
        "src/thoughtpins/memory/vector_store.py",
        "Qdrant init failed: {}. Falling back to FAISS.",
    ): "vector service connection",
    ("src/thoughtpins/worker.py", "Celery signal registration skipped: {}"): "Celery import or signal wiring",
    ("src/thoughtpins/article_providers.py", "Invalid APIFY_READER_INPUT_TEMPLATE; using default input: {}"): (
        "the operator's own configuration value"
    ),
    (
        "src/thoughtpins/memory/vector_store.py",
        "Could not load local embedding runtime: {}. Falling back to configured embeddings.",
    ): "embedding library import",
}
# Reviewed exceptions, keyed by file and argument name, each with its reason.
ALLOWED_CONTENT_ARGUMENTS = {
    ("src/thoughtpins/memory/search.py", "name"): "a retrieval channel label, not user content",
    ("src/thoughtpins/server.py", "name"): "the generated backup archive filename",
    ("src/thoughtpins/email_delivery.py", "text"): (
        "development preview under EMAIL_PROVIDER=none; production validation rejects "
        "that provider while magic links are enabled"
    ),
}


def main(root: Path = ROOT) -> int:
    findings: list[str] = []
    for path in _python_sources(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
        except SyntaxError as exc:
            findings.append(f"{rel}: could not parse Python source: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_logger_call(node):
                for argument in _content_arguments(node):
                    if (rel, argument) not in ALLOWED_CONTENT_ARGUMENTS:
                        findings.append(f"{rel}:{node.lineno}: log argument {argument!r} carries user content")
                if _logs_exception_text(node) and (rel, _literal_template(node)) not in ALLOWED_EXCEPTION_LOGS:
                    findings.append(
                        f"{rel}:{node.lineno}: log prints an exception's message; log type(exc).__name__ instead"
                    )
                template = _literal_template(node)
                if not template:
                    continue
                lowered = template.lower()
                for pattern in SENSITIVE_TEMPLATE_PATTERNS:
                    if pattern.search(lowered):
                        findings.append(f"{rel}:{node.lineno}: log template exposes sensitive identifier marker")
                        break
                if "/bot/" in f"/{rel}" and BOT_USER_ID_PATTERN.search(lowered):
                    findings.append(f"{rel}:{node.lineno}: bot log template should fingerprint Telegram user IDs")
    if findings:
        print("Log privacy check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Log privacy check passed.")
    return 0


def _python_sources(root: Path):
    source_root = root / "src" / "thoughtpins"
    if not source_root.exists():
        source_root = root
    for path in source_root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def _is_logger_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in LOGGER_METHODS:
        return False
    target = func.value
    # logger.opt(...).info(...) and logger.bind(...).info(...) log the same way.
    while (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Attribute)
        and target.func.attr in {"opt", "bind", "patch", "contextualize"}
    ):
        target = target.func.value
    return isinstance(target, ast.Name) and target.id == "logger"


# Wrappers that pass their argument's content through unchanged. len(), type()
# and the like reduce content to something safe and are deliberately absent.
_TRANSPARENT_CALLS = frozenset({"str", "repr", "ascii", "format"})
_TRANSPARENT_METHODS = frozenset({"strip", "lstrip", "rstrip", "lower", "upper", "casefold", "title", "replace"})


def _logged_values(node: ast.Call) -> list[ast.expr]:
    values: list[ast.expr] = [*node.args[1:], *(keyword.value for keyword in node.keywords)]
    if node.args:
        values.append(node.args[0])
    return values


def _content_arguments(node: ast.Call) -> list[str]:
    """Content-named values reaching a logger; len(text) and identifiers pass."""

    return [
        name for value in _logged_values(node) for name in _content_identifiers(value) if name in CONTENT_ARGUMENT_NAMES
    ]


def _logs_exception_text(node: ast.Call) -> bool:
    return any(
        name in EXCEPTION_ARGUMENT_NAMES for value in _logged_values(node) for name in _content_identifiers(value)
    )


def _content_identifiers(node: ast.expr) -> list[str]:
    """Names whose value would be printed, looking through formatting and wrappers."""

    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return [node.slice.value]
    return [name for part in _printed_parts(node) for name in _content_identifiers(part)]


def _printed_parts(node: ast.expr) -> list[ast.expr]:
    """The sub-expressions whose text ends up in this expression's printed value."""

    if isinstance(node, ast.Subscript):
        # text[:200] and rows[0] carry what their container carries.
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [part.value for part in node.values if isinstance(part, ast.FormattedValue)]
    if isinstance(node, ast.BinOp):
        # "x " + text, and "%s" % text.
        return [node.left, node.right]
    if isinstance(node, ast.IfExp):
        return [node.body, node.orelse]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return list(node.elts)
    if isinstance(node, ast.Dict):
        return [value for value in node.values if value is not None]
    if isinstance(node, ast.Starred):
        return [node.value]
    if isinstance(node, ast.Call):
        return _printed_call_parts(node)
    return []


def _printed_call_parts(node: ast.Call) -> list[ast.expr]:
    func = node.func
    if isinstance(func, ast.Name) and func.id in _TRANSPARENT_CALLS:
        return node.args[:1]
    if not isinstance(func, ast.Attribute):
        return []
    if func.attr in _TRANSPARENT_METHODS:
        return [func.value]
    if func.attr == "join":
        return node.args[:1]
    if func.attr == "format":
        # "Created {}".format(name): the template and every argument.
        return [func.value, *node.args, *(keyword.value for keyword in node.keywords)]
    return []


def _literal_template(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check runtime log templates for sensitive identifier exposure.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to inspect.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(args.root.resolve()))
