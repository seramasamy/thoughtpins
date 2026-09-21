"""Exercise request admission with a real, deliberately small connection pool."""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest
from anyio.to_thread import current_default_thread_limiter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from thoughtpins.api_runtime import request_worker_limit


@pytest.mark.parametrize(
    ("size", "overflow", "existing", "expected"),
    [
        (10, 20, 40, 15),
        (5, 10, 40, 7),
        (10, 20, 6, 6),
        (80, 0, 40, 40),
        (2, 0, 40, 1),
        (0, 10, 40, 40),
        (5, -1, 40, 40),
    ],
)
def test_finite_pool_leaves_headroom_without_raising_an_existing_limit(size, overflow, existing, expected):
    assert request_worker_limit(pool_size=size, max_overflow=overflow, current_limit=existing) == expected


@pytest.mark.parametrize(("size", "overflow"), [(-1, 10), (5, -2), (1, 0)])
def test_invalid_or_single_connection_request_pool_is_rejected(size, overflow):
    with pytest.raises(ValueError):
        request_worker_limit(pool_size=size, max_overflow=overflow, current_limit=40)


def _configure_pool_budget(monkeypatch, size=4, overflow=0):
    from thoughtpins.config import config

    # Only the budget sees this synthetic production URL. The test store is
    # already initialized with isolated_db and no network connection is opened.
    monkeypatch.setattr(type(config), "database_url_sync", classmethod(lambda cls: "postgresql://test.invalid/test"))
    monkeypatch.setattr(config, "DB_POOL_SIZE", size)
    monkeypatch.setattr(config, "DB_MAX_OVERFLOW", overflow)


@pytest.mark.parametrize("raise_during_lifespan", [False, True])
async def test_actual_app_lifespan_restores_budget_and_offloads_lifecycle(monkeypatch, raise_during_lifespan):
    from thoughtpins import api, api_runtime

    _configure_pool_budget(monkeypatch)
    threads = []
    monkeypatch.setattr(api_runtime, "_startup", lambda: threads.append(threading.get_ident()))
    monkeypatch.setattr(api_runtime, "_shutdown", lambda: threads.append(threading.get_ident()))
    limiter = current_default_thread_limiter()
    original = limiter.total_tokens
    try:
        async with api.app.router.lifespan_context(api.app):
            assert limiter.total_tokens == 2
            if raise_during_lifespan:
                raise RuntimeError("synthetic lifespan failure")
    except RuntimeError:
        assert raise_during_lifespan
    assert limiter.total_tokens == original
    assert len(threads) == 2
    assert all(thread != threading.get_ident() for thread in threads)


async def test_startup_failure_restores_budget(monkeypatch):
    from thoughtpins import api, api_runtime

    _configure_pool_budget(monkeypatch)

    def fail_startup():
        raise RuntimeError("synthetic startup failure")

    monkeypatch.setattr(api_runtime, "_startup", fail_startup)
    limiter = current_default_thread_limiter()
    original = limiter.total_tokens
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        async with api.app.router.lifespan_context(api.app):
            pytest.fail("failed startup must not serve")
    assert limiter.total_tokens == original


async def test_saturated_requests_allow_nested_transactions_health_and_queued_cancellation(isolated_db, monkeypatch):
    from thoughtpins import api, api_runtime
    from thoughtpins.api_routes import account
    from thoughtpins.tenancy import get_current_tenant_id

    # SQLite SELECT 1 exercises SQLAlchemy's real checkout limits, without
    # pretending to measure PostgreSQL query speed or shared database capacity.
    engine = create_engine(
        "sqlite://",
        poolclass=QueuePool,
        pool_size=4,
        max_overflow=0,
        pool_timeout=0.3,
        connect_args={"check_same_thread": False},
    )
    entered, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    observed = []
    original_session = account.get_session

    def hold_route_then_meter():
        with Session(engine) as outer:
            outer.execute(text("SELECT 1"))
            with lock:
                observed.append((threading.get_ident(), get_current_tenant_id()))
                if len(observed) == 2:
                    entered.set()
            if not release.wait(10):
                raise TimeoutError("test did not release the held requests")
            # A provider's usage transaction needs a second connection while
            # the route still owns the first. Saturating every connection with
            # an outer request would make every worker time out here.
            with Session(engine) as usage:
                assert usage.scalar(text("SELECT 1")) == 1
        return original_session()

    limiter = current_default_thread_limiter()
    original_tokens = limiter.total_tokens
    tasks = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
            owner = (await client.get("/v1/me")).json()["id"]
            _configure_pool_budget(monkeypatch)
            monkeypatch.setattr(api_runtime, "_startup", lambda: None)
            monkeypatch.setattr(api_runtime, "_shutdown", lambda: None)
            monkeypatch.setattr(account, "get_session", hold_route_then_meter)
            async with api.app.router.lifespan_context(api.app):
                with engine.connect() as background:
                    assert background.scalar(text("SELECT 1")) == 1
                    tasks = [asyncio.create_task(client.get("/v1/me")) for _ in range(6)]
                    try:
                        assert await asyncio.to_thread(entered.wait, 5)
                        assert limiter.borrowed_tokens == 2
                        assert len(observed) == 2
                        health = await asyncio.wait_for(client.get("/health"), timeout=1)
                        assert health.status_code == 200
                        queued = asyncio.create_task(client.get("/v1/me"))
                        tasks.append(queued)
                        # A health round trip gives the extra request time to
                        # reach admission while both available workers are held.
                        assert (await client.get("/health")).status_code == 200
                        queued.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await queued
                        assert len(observed) == 2
                    finally:
                        release.set()
                        outcomes = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=15)
                    responses = [value for value in outcomes if isinstance(value, httpx.Response)]
                    assert len(responses) == 6
                    assert all(response.status_code == 200 and response.json()["id"] == owner for response in responses)
                    assert len(observed) == 6
                    assert all(thread != threading.get_ident() and tenant == owner for thread, tenant in observed)
                assert engine.pool.checkedout() == 0
                assert limiter.borrowed_tokens == 0
        assert limiter.total_tokens == original_tokens
    finally:
        release.set()
        engine.dispose()
