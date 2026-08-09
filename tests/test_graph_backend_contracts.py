"""Deletion and recall contracts for auxiliary graph backends.

The README keeps external graph backends behind a flag "until deletion and
recall contracts are proven". These are those contracts, written as properties
rather than as a description of the current implementation:

- an account cannot be reported deleted while a backend still holds its episodes
- a backend that never accepted an episode does not block deletion
- an unproven backend never answers a user's query
- every write and read carries the tenant's id

graphiti-core is not installed here and no graph server is reachable, so these
use fakes. That is the point: the contract is about what the *abstraction*
guarantees, so any future driver has a test that fails before its data escapes.
"""

from __future__ import annotations

import pytest

from thoughtpins.memory.graph_backend import (
    GraphBackendStatus,
    GraphEpisode,
    GraphitiBackend,
    GraphSearchHit,
    InternalSqlGraphBackend,
    ShadowGraphBackend,
)


class FakeBackend:
    """A graph backend whose delete outcome and recall are dictated by the test."""

    def __init__(self, provider: str = "fake", *, deletes: bool = True, hits: list[str] | None = None):
        self.provider = provider
        self._deletes = deletes
        self._hits = hits or []
        self.added: list[GraphEpisode] = []
        self.searched: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def status(self) -> GraphBackendStatus:
        return GraphBackendStatus(provider=self.provider, status="ok")

    def add_episode(self, episode: GraphEpisode) -> bool:
        self.added.append(episode)
        return True

    def search(self, query: str, *, user_id: str, limit: int = 10) -> list[GraphSearchHit]:
        self.searched.append((query, user_id))
        return [GraphSearchHit(text=text, source=self.provider) for text in self._hits][:limit]

    def delete_user(self, user_id: str) -> bool:
        self.deleted.append(user_id)
        return self._deletes


# -- Deletion contract ----------------------------------------------------


def test_shadow_delete_fails_when_the_shadow_cannot_delete():
    """A shadow holding real episodes must not be papered over by the primary."""
    primary = FakeBackend("internal_sql", deletes=True)
    shadow = FakeBackend("graphiti", deletes=False)

    assert ShadowGraphBackend(primary, shadow).delete_user("user-1") is False
    assert shadow.deleted == ["user-1"], "the shadow must actually be asked"


def test_shadow_delete_fails_when_the_shadow_raises():
    class Exploding(FakeBackend):
        def delete_user(self, user_id: str) -> bool:
            raise RuntimeError("graph server unreachable")

    result = ShadowGraphBackend(FakeBackend(deletes=True), Exploding("graphiti")).delete_user("user-1")
    assert result is False, "an error reaching the shadow is not a successful deletion"


def test_shadow_delete_succeeds_only_when_both_halves_do():
    assert ShadowGraphBackend(FakeBackend(deletes=True), FakeBackend(deletes=True)).delete_user("u") is True
    assert ShadowGraphBackend(FakeBackend(deletes=False), FakeBackend(deletes=True)).delete_user("u") is False


def test_configured_graphiti_refuses_to_claim_a_deletion_it_cannot_perform():
    backend = GraphitiBackend.__new__(GraphitiBackend)
    backend._graphiti = object()  # configured and potentially holding episodes
    backend._init_error = ""

    assert backend.delete_user("user-1") is False


def test_uninitialised_graphiti_does_not_block_deletion():
    """It refused every add_episode, so it holds nothing and has nothing to lose."""
    backend = GraphitiBackend.__new__(GraphitiBackend)
    backend._graphiti = None
    backend._init_error = "graphiti-core is not installed"

    assert backend.add_episode(GraphEpisode(user_id="u", episode_id="e", name="n", body="b")) is False
    assert backend.delete_user("user-1") is True


def test_account_deletion_refuses_when_the_graph_backend_cannot_confirm(isolated_db, monkeypatch):
    """The whole point: no 'your account was deleted' while episodes survive."""
    from thoughtpins import data_lifecycle
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(
        "thoughtpins.memory.graph_backend.get_graph_backend",
        lambda session: FakeBackend("graphiti", deletes=False),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        with pytest.raises(data_lifecycle.DataDeletionUnavailable):
            data_lifecycle.delete_user_data(session, user.id)
    finally:
        session.close()


def test_account_deletion_proceeds_on_the_default_backend(isolated_db):
    """internal_sql is the default and must not be made harder to delete from."""
    from thoughtpins.data_lifecycle import delete_user_data
    from thoughtpins.db import User
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        user_id = user.id
        delete_user_data(session, user_id)
        session.commit()
        assert session.query(User).filter(User.id == user_id).one().is_active is False
    finally:
        session.close()


def test_internal_sql_reports_deletion_because_its_rows_cascade(isolated_db):
    from thoughtpins.store import get_session

    session = get_session()
    try:
        assert InternalSqlGraphBackend(session).delete_user("user-1") is True
    finally:
        session.close()


# -- Recall contract ------------------------------------------------------


def test_shadow_recall_never_reaches_the_caller():
    """An unproven backend is measured, not answered from."""
    primary = FakeBackend("internal_sql", hits=["primary fact"])
    shadow = FakeBackend("graphiti", hits=["shadow fact"])

    hits = ShadowGraphBackend(primary, shadow).search("q", user_id="user-1", limit=10)

    assert [hit.text for hit in hits] == ["primary fact"]
    assert shadow.searched, "the shadow is still exercised so its failures surface"


def test_shadow_recall_is_withheld_even_when_the_primary_returns_nothing():
    """The tempting case: an empty primary must not be topped up from the shadow."""
    shadow = FakeBackend("graphiti", hits=["shadow fact one", "shadow fact two"])

    hits = ShadowGraphBackend(FakeBackend(hits=[]), shadow).search("q", user_id="user-1", limit=10)

    assert hits == []


def test_shadow_search_failure_does_not_break_recall():
    class Exploding(FakeBackend):
        def search(self, query: str, *, user_id: str, limit: int = 10):
            raise RuntimeError("graph server unreachable")

    hits = ShadowGraphBackend(FakeBackend(hits=["primary fact"]), Exploding()).search("q", user_id="u", limit=5)

    assert [hit.text for hit in hits] == ["primary fact"]


def test_shadow_respects_the_requested_limit():
    primary = FakeBackend(hits=["a", "b", "c", "d"])
    assert len(ShadowGraphBackend(primary, FakeBackend()).search("q", user_id="u", limit=2)) == 2


# -- Tenant scoping contract ---------------------------------------------


def test_every_read_and_write_carries_the_tenant_id():
    primary = FakeBackend("internal_sql")
    shadow = FakeBackend("graphiti")
    backend = ShadowGraphBackend(primary, shadow)

    backend.add_episode(GraphEpisode(user_id="user-1", episode_id="e1", name="n", body="b"))
    backend.search("q", user_id="user-1", limit=5)
    backend.delete_user("user-1")

    for half in (primary, shadow):
        assert [episode.user_id for episode in half.added] == ["user-1"]
        assert [user_id for _, user_id in half.searched] == ["user-1"]
        assert half.deleted == ["user-1"]


def test_production_config_still_refuses_external_graph_backends():
    """The flag this contract set is written against must stay shut."""
    from thoughtpins.config import graph_backend_problems

    assert graph_backend_problems("internal_sql", False) == []
    assert graph_backend_problems("graphiti", False), "graphiti must remain blocked in production"
    assert graph_backend_problems("internal_sql", True), "shadow mode must remain blocked in production"
