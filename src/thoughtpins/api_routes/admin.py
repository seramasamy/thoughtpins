"""Owner-only operational routes.

Kept separate from `/v1/metrics`, which any authenticated user may read: spend is
per-user financial data and must never be served on a shared surface.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from thoughtpins.store import get_session
from thoughtpins.usage import build_usage_report


def create_admin_router(*, current_user_dependency: Callable) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/admin/usage")
    async def admin_usage(request: Request, user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        if not getattr(request.state, "user_is_admin", False):
            raise HTTPException(status_code=403, detail="Admin access required")
        session = get_session()
        try:
            return build_usage_report(session)
        finally:
            session.close()

    return router
