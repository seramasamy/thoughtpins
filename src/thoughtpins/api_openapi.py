"""OpenAPI additions for cross-platform mutation semantics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def install_openapi_contract(app: FastAPI, *, is_public_path: Callable[[str], bool]) -> None:
    def public_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _document_idempotency(schema, is_public_path=is_public_path)
        app.openapi_schema = schema
        return schema

    app.openapi = public_openapi


def _document_idempotency(schema: dict[str, Any], *, is_public_path: Callable[[str], bool]) -> None:
    parameter = {
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "description": (
            "Stable 8-128 character key for safely retrying an authenticated mutation. "
            "Reusing a key with different request content returns 409."
        ),
        "schema": {
            "type": "string",
            "minLength": 8,
            "maxLength": 128,
            "pattern": "^[A-Za-z0-9_.:-]+$",
        },
    }
    for path, operations in schema.get("paths", {}).items():
        if is_public_path(path):
            continue
        for method in ("post", "put", "patch", "delete"):
            operation = operations.get(method)
            if not isinstance(operation, dict):
                continue
            parameters = operation.setdefault("parameters", [])
            if not any(item.get("name") == "Idempotency-Key" and item.get("in") == "header" for item in parameters):
                parameters.append(dict(parameter))
            for status, response in operation.get("responses", {}).items():
                if str(status).startswith(("2", "3")) and isinstance(response, dict):
                    response.setdefault("headers", {})["X-Idempotent-Replay"] = {
                        "description": "True when the response was replayed from a completed mutation.",
                        "schema": {"type": "string", "enum": ["true"]},
                    }
