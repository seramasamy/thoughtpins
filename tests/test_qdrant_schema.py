from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

from thoughtpins.memory.qdrant_schema import ensure_remote_tenant_index


def test_existing_tenant_index_is_preserved_and_local_storage_is_untouched() -> None:
    client = Mock(spec=QdrantClient)
    client.get_collection.return_value = SimpleNamespace(
        payload_schema={"user_id": SimpleNamespace(data_type=PayloadSchemaType.KEYWORD)}
    )
    ensure_remote_tenant_index(client, "journal_memories_1536", remote=True)
    client.create_payload_index.assert_not_called()

    client.reset_mock()
    ensure_remote_tenant_index(client, "journal_memories_384", remote=False)
    client.get_collection.assert_not_called()
    client.create_payload_index.assert_not_called()


def test_incompatible_index_is_rejected_without_replacing_it() -> None:
    client = Mock(spec=QdrantClient)
    client.get_collection.return_value = SimpleNamespace(
        payload_schema={"user_id": SimpleNamespace(data_type=PayloadSchemaType.INTEGER)}
    )
    with pytest.raises(RuntimeError, match="must use the keyword type"):
        ensure_remote_tenant_index(client, "journal_memories_1536", remote=True)
    client.create_payload_index.assert_not_called()
    client.delete_payload_index.assert_not_called()


def test_missing_index_permission_failure_cannot_report_readiness() -> None:
    client = Mock(spec=QdrantClient)
    client.get_collection.return_value = SimpleNamespace(payload_schema={})
    client.create_payload_index.side_effect = PermissionError("Index creation unavailable")
    with pytest.raises(PermissionError, match="Index creation unavailable"):
        ensure_remote_tenant_index(client, "journal_memories_1536", remote=True)
