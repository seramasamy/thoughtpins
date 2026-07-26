"""Deterministic JSON Canvas 1.0 export and bounded import helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from thoughtpins.db import Entity, Relationship

MEMORY_CANVAS_PATH = PurePosixPath("_Views/Memory Map.canvas")
MAX_CANVAS_BYTES = 5 * 1024 * 1024
MAX_CANVAS_NODES = 2_000
MAX_CANVAS_EDGES = 5_000
MAX_GENERATED_NODES = 250
MAX_GENERATED_EDGES = 1_000
MAX_IMPORTED_TEXT_CHARS = 250_000
NODE_TYPES = {"text", "file", "link", "group"}
SIDES = {"top", "right", "bottom", "left"}
END_STYLES = {"none", "arrow"}
_SPACE = re.compile(r"[_\s-]+")


def write_memory_canvas(
    vault: str | Path,
    entities: Sequence[Entity],
    relationships: Sequence[Relationship],
    entity_paths: Mapping[str, PurePosixPath],
) -> str:
    """Write a stable entity/relationship overview as JSON Canvas 1.0."""
    root = Path(vault)
    payload = build_memory_canvas(entities, relationships, entity_paths)
    errors = validate_canvas_payload(payload, existing_files=_existing_files(root), strict_generated=True)
    if errors:
        raise ValueError(f"invalid generated Canvas: {'; '.join(errors)}")
    target = root / Path(MEMORY_CANVAS_PATH.as_posix())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return MEMORY_CANVAS_PATH.as_posix()


def build_memory_canvas(
    entities: Sequence[Entity],
    relationships: Sequence[Relationship],
    entity_paths: Mapping[str, PurePosixPath],
) -> dict[str, list[dict[str, Any]]]:
    """Build a deterministic, bounded memory graph without layout-side effects."""
    exported = [entity for entity in entities if entity.id in entity_paths]
    exported.sort(
        key=lambda entity: (
            _entity_group(entity),
            entity_paths[entity.id].as_posix().casefold(),
            entity.id,
        ),
    )
    exported = exported[:MAX_GENERATED_NODES]
    if not exported:
        return {
            "nodes": [
                {
                    "id": _stable_id("empty", "memory-map"),
                    "type": "text",
                    "text": "# Memory Map\n\nPeople, places, projects, and concepts will appear here as memories are added.",
                    "x": 0,
                    "y": 0,
                    "width": 420,
                    "height": 180,
                },
            ],
            "edges": [],
        }

    grouped: dict[str, list[Entity]] = defaultdict(list)
    for entity in exported:
        grouped[_entity_group(entity)].append(entity)

    nodes: list[dict[str, Any]] = []
    entity_node_ids: dict[str, str] = {}
    group_order = sorted(grouped, key=lambda name: (_group_rank(name), name.casefold()))
    column_width = 400
    card_width = 300
    card_height = 100
    vertical_gap = 40
    group_padding = 50
    for column, group_name in enumerate(group_order):
        members = grouped[group_name]
        x = column * column_width
        group_height = max(
            220, group_padding * 2 + len(members) * card_height + max(0, len(members) - 1) * vertical_gap
        )
        nodes.append(
            {
                "id": _stable_id("group", group_name),
                "type": "group",
                "label": group_name,
                "x": x,
                "y": 0,
                "width": card_width + group_padding * 2,
                "height": group_height,
            },
        )
        for row, entity in enumerate(members):
            node_id = _stable_id("entity", entity.id)
            entity_node_ids[entity.id] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "type": "file",
                    "file": entity_paths[entity.id].as_posix(),
                    "x": x + group_padding,
                    "y": group_padding + row * (card_height + vertical_gap),
                    "width": card_width,
                    "height": card_height,
                },
            )

    edges: list[dict[str, Any]] = []
    eligible = [
        relationship
        for relationship in relationships
        if relationship.source_entity_id in entity_node_ids and relationship.target_entity_id in entity_node_ids
    ]
    eligible.sort(
        key=lambda relationship: (
            relationship.relation_type.casefold(),
            relationship.source_entity_id,
            relationship.target_entity_id,
            relationship.id,
        ),
    )
    for relationship in eligible[:MAX_GENERATED_EDGES]:
        edges.append(
            {
                "id": _stable_id("relationship", relationship.id),
                "fromNode": entity_node_ids[relationship.source_entity_id],
                "fromSide": "right",
                "toNode": entity_node_ids[relationship.target_entity_id],
                "toSide": "left",
                "toEnd": "arrow",
                "label": humanize_relation(relationship.relation_type),
            },
        )
    return {"nodes": nodes, "edges": edges}


def load_canvas_bytes(payload: bytes) -> dict[str, Any]:
    """Decode an uploaded Canvas with conservative resource bounds."""
    if len(payload) > MAX_CANVAS_BYTES:
        raise ValueError("Canvas file exceeds 5 MiB")
    try:
        value = json.loads(payload.decode("utf-8-sig"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Canvas file is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Canvas root must be an object")
    return value


def validate_canvas_payload(
    payload: Mapping[str, Any],
    *,
    existing_files: set[str] | None = None,
    strict_generated: bool = False,
) -> list[str]:
    """Validate JSON Canvas identities, references, geometry, and file links."""
    nodes, edges, errors = _canvas_collections(payload)
    all_ids: set[str] = set()
    node_ids: set[str] = set()
    for index, node in enumerate(nodes[: MAX_CANVAS_NODES + 1]):
        errors.extend(_validate_canvas_node(node, index, all_ids, node_ids, existing_files))

    for index, edge in enumerate(edges[: MAX_CANVAS_EDGES + 1]):
        errors.extend(_validate_canvas_edge(edge, index, all_ids, node_ids))

    if strict_generated and not nodes:
        errors.append("generated canvas must contain at least one node")
    return errors


def _canvas_collections(
    payload: Mapping[str, Any],
) -> tuple[list[Any], list[Any], list[str]]:
    errors: list[str] = []
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    edges = raw_edges if isinstance(raw_edges, list) else []
    if not isinstance(raw_nodes, list):
        errors.append("nodes must be a list")
    if not isinstance(raw_edges, list):
        errors.append("edges must be a list")
    if len(nodes) > MAX_CANVAS_NODES:
        errors.append(f"canvas exceeds {MAX_CANVAS_NODES} nodes")
    if len(edges) > MAX_CANVAS_EDGES:
        errors.append(f"canvas exceeds {MAX_CANVAS_EDGES} edges")
    return nodes, edges, errors


def _register_canvas_id(
    item_id: str,
    *,
    kind: str,
    index: int,
    all_ids: set[str],
) -> tuple[bool, list[str]]:
    if not item_id:
        return False, [f"{kind} {index} is missing id"]
    if item_id in all_ids:
        return False, [f"duplicate canvas id {item_id}"]
    if len(item_id) > 128:
        return False, [f"{kind} {index} id exceeds 128 characters"]
    all_ids.add(item_id)
    return True, []


def _validate_canvas_node(
    node: Any,
    index: int,
    all_ids: set[str],
    node_ids: set[str],
    existing_files: set[str] | None,
) -> list[str]:
    if not isinstance(node, Mapping):
        return [f"node {index} must be an object"]
    errors: list[str] = []
    node_id = str(node.get("id") or "")
    registered, id_errors = _register_canvas_id(
        node_id,
        kind="node",
        index=index,
        all_ids=all_ids,
    )
    errors.extend(id_errors)
    if registered:
        node_ids.add(node_id)
    label = node_id or str(index)
    node_type = str(node.get("type") or "")
    if node_type not in NODE_TYPES:
        errors.append(f"node {label} has unsupported type {node_type!r}")
    errors.extend(_validate_node_geometry(node, label))
    required = {"text": "text", "file": "file", "link": "url", "group": "label"}.get(node_type)
    if required and not str(node.get(required) or "").strip():
        errors.append(f"node {label} is missing {required}")
    if node_type == "file" and existing_files is not None:
        target = str(node.get("file") or "").replace("\\", "/").removeprefix("/").casefold()
        if target and target not in existing_files:
            errors.append(f"node {label} references missing file {node.get('file')}")
    return errors


def _validate_node_geometry(node: Mapping[str, Any], label: str) -> list[str]:
    errors = [
        f"node {label} has invalid {key}"
        for key in ("x", "y", "width", "height")
        if not _valid_coordinate(node.get(key))
    ]
    for key in ("width", "height"):
        value = node.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool) and value <= 0:
            errors.append(f"node {label} {key} must be positive")
    return errors


def _validate_canvas_edge(
    edge: Any,
    index: int,
    all_ids: set[str],
    node_ids: set[str],
) -> list[str]:
    if not isinstance(edge, Mapping):
        return [f"edge {index} must be an object"]
    edge_id = str(edge.get("id") or "")
    _, errors = _register_canvas_id(edge_id, kind="edge", index=index, all_ids=all_ids)
    label = edge_id or str(index)
    for key in ("fromNode", "toNode"):
        reference = str(edge.get(key) or "")
        if reference not in node_ids:
            errors.append(f"edge {label} has unknown {key} {reference!r}")
    for key in ("fromSide", "toSide"):
        value = edge.get(key)
        if value is not None and str(value) not in SIDES:
            errors.append(f"edge {label} has invalid {key}")
    for key in ("fromEnd", "toEnd"):
        value = edge.get(key)
        if value is not None and str(value) not in END_STYLES:
            errors.append(f"edge {label} has invalid {key}")
    return errors


def canvas_to_markdown(path: PurePosixPath, payload: Mapping[str, Any]) -> tuple[str, str]:
    """Flatten a user-authored Canvas into a bounded, recallable source note."""
    validation = validate_canvas_payload(payload)
    if validation:
        raise ValueError("; ".join(validation[:10]))
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    labels: dict[str, str] = {}
    sections: list[str] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        if node_type == "text":
            value = str(node.get("text") or "").strip()
        elif node_type == "file":
            file_target = _safe_inline_text(str(node.get("file") or "").removesuffix(".md"), 1_000)
            value = f"Vault file: [[{file_target}]]"
        elif node_type == "link":
            value = f"External link: {_safe_inline_text(str(node.get('url') or ''), 4_000)}"
        else:
            value = f"Group: {_safe_inline_text(str(node.get('label') or ''), 1_000)}"
        labels[node_id] = _first_line(value)
        if value:
            sections.append(value)

    relationship_lines: list[str] = []
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        source = labels.get(str(edge.get("fromNode") or ""), "Unknown node")
        target = labels.get(str(edge.get("toNode") or ""), "Unknown node")
        label = _safe_inline_text(str(edge.get("label") or "relates to"), 500)
        relationship_lines.append(f"- {source} -- {label} --> {target}")
    title = path.stem[:512] or "Canvas"
    body_parts = [f"# {title}", "", "## Canvas Content", ""]
    body_parts.extend(sections or ["No readable nodes were present."])
    if relationship_lines:
        body_parts.extend(["", "## Connections", *relationship_lines])
    body = "\n".join(body_parts)
    return title, body[:MAX_IMPORTED_TEXT_CHARS]


def humanize_relation(value: str) -> str:
    """Turn storage-oriented relationship labels into readable edge labels."""
    normalized = _SPACE.sub(" ", str(value or "related to")).strip().casefold()
    return normalized[:80] or "related to"


def _stable_id(kind: str, value: str) -> str:
    return hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()[:16]


def _entity_group(entity: Entity) -> str:
    normalized = str(entity.type or "concept").strip().casefold()
    return {
        "person": "People",
        "place": "Places",
        "organization": "Organizations",
        "company": "Organizations",
        "project": "Projects",
        "idea": "Projects",
        "event": "Events",
        "thing": "Things",
        "object": "Things",
        "technology": "Things",
        "concept": "Concepts",
        "topic": "Concepts",
    }.get(normalized, "Concepts")


def _group_rank(value: str) -> int:
    order = ["People", "Places", "Organizations", "Projects", "Events", "Things", "Concepts"]
    try:
        return order.index(value)
    except ValueError:
        return len(order)


def _existing_files(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix().casefold() for path in root.rglob("*") if path.is_file()}


def _first_line(value: str) -> str:
    for line in value.splitlines():
        cleaned = line.lstrip("#- ").strip()
        if cleaned:
            return cleaned[:160]
    return "Canvas node"


def _safe_inline_text(value: str, max_chars: int) -> str:
    return " ".join(value.replace("[[", "(").replace("]]", ")").split())[:max_chars]


def _valid_coordinate(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return abs(value) <= 1_000_000_000


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Canvas contains non-finite JSON number {value}")


__all__ = [
    "MEMORY_CANVAS_PATH",
    "build_memory_canvas",
    "canvas_to_markdown",
    "humanize_relation",
    "load_canvas_bytes",
    "validate_canvas_payload",
    "write_memory_canvas",
]
