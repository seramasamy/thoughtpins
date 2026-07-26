"""Verify Qdrant collection snapshot recovery with an isolated fixture.

The drill never mutates an application collection. It creates a random
``thoughtpins_recovery_drill_*`` collection, snapshots it, deletes it, restores
the uploaded snapshot, verifies vectors and payloads, and removes the fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from qdrant_client import QdrantClient, models

SAFE_COLLECTION_RE = re.compile(r"^thoughtpins_recovery_drill_[a-f0-9]{12}$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated Qdrant snapshot restore drill.")
    parser.add_argument("--url", default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--api-key", default=os.getenv("QDRANT_API_KEY", ""))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    collection = f"thoughtpins_recovery_drill_{uuid4().hex[:12]}"
    assert_safe_collection_name(collection)
    client = QdrantClient(
        url=args.url.rstrip("/"),
        api_key=args.api_key or None,
        timeout=args.timeout_seconds,
    )
    snapshot_path: Path | None = None
    snapshot_name = ""
    expected_payload = {"fixture": "snapshot-restore", "tenant_id": "recovery-drill"}

    try:
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE),
        )
        client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(id=1, vector=[1.0, 0.0, 0.0, 0.0], payload=expected_payload),
                models.PointStruct(id=2, vector=[0.0, 1.0, 0.0, 0.0], payload={"fixture": "second-point"}),
            ],
            wait=True,
        )
        if client.count(collection, exact=True).count != 2:
            raise RuntimeError("Qdrant fixture count was not durable before snapshot")

        snapshot = client.create_snapshot(collection, wait=True)
        if snapshot is None or not snapshot.name:
            raise RuntimeError("Qdrant did not return a collection snapshot")
        snapshot_name = snapshot.name
        response = httpx.get(
            f"{args.url.rstrip('/')}/collections/{quote(collection, safe='')}/snapshots/{quote(snapshot_name, safe='')}",
            headers={"api-key": args.api_key} if args.api_key else None,
            timeout=args.timeout_seconds,
        )
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("Downloaded Qdrant snapshot was empty")

        with tempfile.NamedTemporaryFile(prefix="thoughtpins-qdrant-", suffix=".snapshot", delete=False) as handle:
            handle.write(response.content)
            snapshot_path = Path(handle.name)

        client.delete_collection(collection)
        with snapshot_path.open("rb") as handle:
            client.http.snapshots_api.recover_from_uploaded_snapshot(
                collection_name=collection,
                wait=True,
                priority=models.SnapshotPriority.SNAPSHOT,
                checksum=snapshot.checksum,
                snapshot=handle,
            )

        if client.count(collection, exact=True).count != 2:
            raise RuntimeError("Restored Qdrant collection did not preserve the fixture count")
        restored = client.retrieve(collection, ids=[1], with_payload=True, with_vectors=True)
        if len(restored) != 1 or restored[0].payload != expected_payload:
            raise RuntimeError("Restored Qdrant collection did not preserve fixture payload provenance")

        print(
            json.dumps(
                {
                    "status": "passed",
                    "collection_prefix": "thoughtpins_recovery_drill_",
                    "points_restored": 2,
                    "snapshot_bytes": snapshot_path.stat().st_size,
                    "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        if SAFE_COLLECTION_RE.fullmatch(collection):
            try:
                if client.collection_exists(collection):
                    client.delete_collection(collection)
            except Exception:
                pass
        if snapshot_path is not None:
            snapshot_path.unlink(missing_ok=True)
        try:
            client.close()
        except Exception:
            pass


def assert_safe_collection_name(name: str) -> None:
    if not SAFE_COLLECTION_RE.fullmatch(name):
        raise ValueError("Qdrant recovery fixtures must use the thoughtpins_recovery_drill_<hex> namespace")


if __name__ == "__main__":
    raise SystemExit(main())
