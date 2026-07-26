"""Common response envelopes for the public HTTP contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

INTERNAL_ERROR_MESSAGE = "The request could not be completed. Please try again."


class ErrorDetail(BaseModel):
    code: str = Field(..., examples=["validation_error"])
    message: str = Field(..., examples=["Request validation failed"])
    request_id: str = Field(..., examples=["b7f0c7a9dce0457aa1d0eb0bb6ed9957"])
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ErrorEnvelope,
        "description": "Bad request.",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "bad_request",
                        "message": "confirm must equal DELETE",
                        "request_id": "req_123",
                    }
                }
            }
        },
    },
    401: {"model": ErrorEnvelope, "description": "Missing or invalid credentials."},
    403: {"model": ErrorEnvelope, "description": "Authenticated but forbidden."},
    404: {"model": ErrorEnvelope, "description": "Resource not found for this user."},
    409: {"model": ErrorEnvelope, "description": "Conflict with existing data."},
    413: {"model": ErrorEnvelope, "description": "Request body is too large."},
    422: {"model": ErrorEnvelope, "description": "Request validation failed."},
    429: {"model": ErrorEnvelope, "description": "Rate limit exceeded."},
    500: {"model": ErrorEnvelope, "description": "Unexpected server error."},
    503: {"model": ErrorEnvelope, "description": "Service temporarily unavailable or maintenance mode."},
}
