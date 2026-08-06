"""The shape of a failed API response.

Every error the service returns crosses this module, so the envelope is defined
once rather than assembled at each raise site. Clients — the web app, both
native shells, and the private adapters — parse `error.code` to decide what to
do, which makes the code a contract and not a log line: renaming one is a
breaking change even though nothing in the type system says so.

Split out of :mod:`thoughtpins.api`, which should describe how the application
is assembled and not what a 429 looks like on the wire.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

# Status codes are an HTTP concern; these codes are the product's own
# vocabulary, stable across transports and versions. Anything unmapped
# degrades to a generic code rather than inventing one per call site.
_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    402: "usage_budget_exceeded",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    429: "rate_limit_exceeded",
}


def request_id(request: Request) -> str:
    """The id assigned by middleware, or empty before it has run."""
    return getattr(request.state, "request_id", "")


def http_error_code(status_code: int) -> str:
    """The product's name for an HTTP status."""
    return _STATUS_CODES.get(status_code, "internal_error" if status_code >= 500 else "bad_request")


def json_safe(value: Any) -> Any:
    """Coerce a value into something serialisable.

    Error details are assembled from exceptions and validation output, which
    can carry objects json does not know. Failing to serialise an error
    response would replace a useful message with a 500, so anything unknown is
    stringified rather than raised.
    """
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def error_payload(code: str, message: str, request_id_value: str = "", details: Any | None = None) -> dict[str, Any]:
    """The response body every failure returns."""
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_value,
        }
    }
    if details is not None:
        payload["error"]["details"] = json_safe(details)
    return payload


def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id_value: str,
    *,
    retry_after: int | None = None,
    details: Any | None = None,
) -> JSONResponse:
    """A complete error response, with the request id echoed in the header.

    The id appears in both the header and the body on purpose: support reads it
    from the body a user pasted, and a proxy or crash log only ever sees the
    header.
    """
    headers = {"X-Request-ID": request_id_value}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content=error_payload(code, message, request_id_value, details),
    )


__all__ = [
    "error_payload",
    "error_response",
    "http_error_code",
    "json_safe",
    "request_id",
]
