"""Required tenant-filter indexes for the remote vector adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdrant_client import QdrantClient


def ensure_remote_tenant_index(client: QdrantClient, collection_name: str, *, remote: bool) -> None:
    """Preserve strict filtering; create only a missing account keyword index.

    Local Qdrant does not implement payload indexes. Remote strict-mode
    collections reject account-scoped queries without this index, even when
    vector insertion and collection health checks succeed.
    """
    if not remote:
        return

    from qdrant_client.models import PayloadSchemaType

    info = client.get_collection(collection_name)
    indexed = info.payload_schema.get("user_id")
    if indexed is not None:
        if indexed.data_type != PayloadSchemaType.KEYWORD:
            raise RuntimeError("The vector account index must use the keyword type; repair its schema before startup")
        return
    client.create_payload_index(
        collection_name=collection_name,
        field_name="user_id",
        field_schema=PayloadSchemaType.KEYWORD,
        wait=True,
    )
