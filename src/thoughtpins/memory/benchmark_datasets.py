"""Pinned external-corpus metadata and deterministic benchmark partitions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BenchmarkPartition = Literal["train", "validation", "holdout", "diagnostic"]


@dataclass(frozen=True)
class DatasetSpec:
    id: str
    kind: str
    source: str
    revision: str
    license: str
    allowed_uses: tuple[str, ...]
    local_path: str
    sha256: str = ""
    bytes: int = 0
    exclusion_reason: str = ""

    @property
    def calibration_allowed(self) -> bool:
        return "calibration" in self.allowed_uses


def load_dataset_specs(path: Path) -> tuple[DatasetSpec, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("memory benchmark manifest schema_version must be 1")
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("memory benchmark manifest must define datasets")

    specs: list[DatasetSpec] = []
    seen: set[str] = set()
    for raw in datasets:
        if not isinstance(raw, dict):
            raise ValueError("each memory benchmark dataset must be an object")
        spec = DatasetSpec(
            id=str(raw.get("id") or "").strip(),
            kind=str(raw.get("kind") or "").strip(),
            source=str(raw.get("source") or "").strip(),
            revision=str(raw.get("revision") or "").strip().lower(),
            license=str(raw.get("license") or "").strip(),
            allowed_uses=tuple(str(value) for value in raw.get("allowed_uses") or ()),
            local_path=str(raw.get("local_path") or "").strip(),
            sha256=str(raw.get("sha256") or "").strip().lower(),
            bytes=int(raw.get("bytes") or 0),
            exclusion_reason=str(raw.get("exclusion_reason") or "").strip(),
        )
        _validate_spec(spec)
        if spec.id in seen:
            raise ValueError(f"duplicate memory benchmark dataset id: {spec.id}")
        seen.add(spec.id)
        specs.append(spec)
    return tuple(specs)


def benchmark_partition(stable_id: str) -> BenchmarkPartition:
    """Assign an item without relying on corpus order or process hash state.

    Buckets 6-9 were used for an initial baseline inspection and are retained
    as diagnostic data. The final holdout is bucket 5, which was not observed
    while the external-corpus adapters and identity feature were developed.
    """
    digest = hashlib.sha256(stable_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % 10
    if bucket < 4:
        return "train"
    if bucket == 4:
        return "validation"
    if bucket == 5:
        return "holdout"
    return "diagnostic"


def sha256_file(path: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dataset_file(path: Path, spec: DatasetSpec) -> tuple[str, ...]:
    problems: list[str] = []
    if not path.is_file():
        return (f"missing dataset file: {path}",)
    if spec.bytes and path.stat().st_size != spec.bytes:
        problems.append(f"size mismatch: expected {spec.bytes}, found {path.stat().st_size}")
    if spec.sha256:
        observed = sha256_file(path)
        if observed != spec.sha256:
            problems.append(f"SHA-256 mismatch: expected {spec.sha256}, found {observed}")
    return tuple(problems)


def _validate_spec(spec: DatasetSpec) -> None:
    if not spec.id or not spec.kind or not spec.source or not spec.local_path:
        raise ValueError("memory benchmark dataset id, kind, source, and local_path are required")
    if spec.kind == "excluded":
        if spec.allowed_uses or not spec.exclusion_reason:
            raise ValueError(f"excluded dataset {spec.id} must have no uses and an exclusion reason")
        return
    if not spec.revision or not spec.license or not spec.allowed_uses:
        raise ValueError(f"dataset {spec.id} must pin a revision, license, and allowed uses")
    if spec.kind == "https_file" and (len(spec.sha256) != 64 or spec.bytes <= 0):
        raise ValueError(f"downloaded dataset {spec.id} must pin SHA-256 and byte length")
