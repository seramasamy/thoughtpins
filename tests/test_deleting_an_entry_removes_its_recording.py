"""Deleting an entry must take its retained recording with it.

The privacy policy says so in as many words -- "Deleting a linked journal entry
removes its retained recording" -- and the AI disclosure repeats it. That is a
stated user right, not a description of a feature, and until now nothing tested
it. The single-entry delete this covers is also new: `deleteEntry` had existed
in the iOS core client with no caller, so the right the policy grants could not
be exercised from the app at all.

Retention itself is opt-in and off in production, so this is the one half of the
chain that cannot be driven against the live service -- an account there can
never have a retained recording to delete. It is proven here instead, against
the same code path the API calls.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def client(isolated_db):
    from thoughtpins.api import app

    return TestClient(app)


def _account(client: TestClient) -> tuple[str, dict[str, str]]:
    email = "recording-chain@thoughtpins.com"
    assert client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE}).status_code == 200
    tokens = client.post("/v1/auth/login", json={"identifier": email, "password": PASSPHRASE}).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post(
        "/v1/legal/acceptances",
        headers=headers,
        json={"document": "ai_disclosure", "version": "2026-07-13"},
    )
    me = client.get("/v1/me", headers=headers).json()
    return me.get("user_id") or me["id"], headers


def _entry_with_recording(client: TestClient, user_id: str, headers: dict[str, str]) -> tuple[str, str]:
    """Create an entry and attach a retained voice asset to it.

    The asset row is written directly rather than through the upload path,
    because retention is gated on an opt-in flag and a transcription provider;
    what is under test is the deletion chain, not the capture flow.
    """
    from thoughtpins.db import VoiceAsset
    from thoughtpins.store import get_session

    created = client.post("/v1/entries", headers=headers, json={"text": "A note that had a recording."})
    assert created.status_code in (200, 202), created.text
    entry_id = created.json()["entry_id"]

    with get_session() as session:
        asset = VoiceAsset(
            user_id=user_id,
            raw_entry_id=entry_id,
            storage_ref=f"{user_id}/probe-recording.bin",
            original_filename="probe-recording.m4a",
            media_type="audio/m4a",
            container="m4a",
            byte_size_original=2048,
            byte_size_encrypted=2100,
            content_fingerprint="probe-fingerprint",
            consent_version="2026-07-13",
        )
        session.add(asset)
        session.commit()
        asset_id = asset.id

    return entry_id, asset_id


def _asset_exists(asset_id: str) -> bool:
    from thoughtpins.db import VoiceAsset
    from thoughtpins.store import get_session

    with get_session() as session:
        return session.get(VoiceAsset, asset_id) is not None


def test_deleting_the_entry_deletes_its_retained_recording(client):
    user_id, headers = _account(client)
    entry_id, asset_id = _entry_with_recording(client, user_id, headers)
    assert _asset_exists(asset_id), "the fixture did not attach a recording, so this would prove nothing"

    response = client.delete(f"/v1/entries/{entry_id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"

    assert not _asset_exists(asset_id), (
        "the entry was deleted and its retained recording was not -- the privacy policy says "
        "deleting a linked journal entry removes its retained recording"
    )


def test_deleting_an_entry_does_not_touch_another_entrys_recording(client):
    """The chain must be precise, or it is a different kind of promise broken."""
    user_id, headers = _account(client)
    doomed_entry, doomed_asset = _entry_with_recording(client, user_id, headers)

    from thoughtpins.db import VoiceAsset
    from thoughtpins.store import get_session

    keeper = client.post("/v1/entries", headers=headers, json={"text": "A different note."}).json()["entry_id"]
    with get_session() as session:
        other = VoiceAsset(
            user_id=user_id,
            raw_entry_id=keeper,
            storage_ref=f"{user_id}/keeper-recording.bin",
            original_filename="keeper.m4a",
            byte_size_original=1024,
            byte_size_encrypted=1100,
            content_fingerprint="keeper-fingerprint",
            consent_version="2026-07-13",
        )
        session.add(other)
        session.commit()
        keeper_asset = other.id

    assert client.delete(f"/v1/entries/{doomed_entry}", headers=headers).status_code == 200
    assert not _asset_exists(doomed_asset)
    assert _asset_exists(keeper_asset), "deleting one entry removed another entry's recording"


def test_an_entry_cannot_be_deleted_by_another_account(client, isolated_db):
    """Tenant scoping on the new path, per AGENTS.md."""
    _, owner_headers = _account(client)
    created = client.post("/v1/entries", headers=owner_headers, json={"text": "Private to its owner."})
    entry_id = created.json()["entry_id"]

    intruder_email = "intruder@thoughtpins.com"
    client.post("/v1/auth/register", json={"email": intruder_email, "password": PASSPHRASE})
    intruder = client.post("/v1/auth/login", json={"identifier": intruder_email, "password": PASSPHRASE}).json()
    intruder_headers = {"Authorization": f"Bearer {intruder['access_token']}"}

    response = client.delete(f"/v1/entries/{entry_id}", headers=intruder_headers)
    assert response.status_code == 404, "another account's entry must not be deletable, or even visible"
    assert client.get("/v1/entries", headers=owner_headers).status_code == 200


def test_deleting_an_entry_twice_reports_it_is_gone(client):
    """A second delete must 404 rather than silently succeed.

    The app removes the row from the list optimistically once the server
    confirms; a silent second success would hide a stale list from the person
    using it.
    """
    _, headers = _account(client)
    entry_id = client.post("/v1/entries", headers=headers, json={"text": "Delete me twice."}).json()["entry_id"]
    assert client.delete(f"/v1/entries/{entry_id}", headers=headers).status_code == 200
    assert client.delete(f"/v1/entries/{entry_id}", headers=headers).status_code == 404
