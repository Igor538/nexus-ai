"""Node registry and static catalog."""

from __future__ import annotations

from typing import Any

from app.services.nodes.base import Node

_REGISTRY: dict[str, Node] = {}
CATEGORY_LABELS = {
    "trigger": "Gatilhos",
    "action": "Ações",
    "logic": "Lógica",
    "ai": "Inteligência Artificial",
}


def register(node: type[Node] | Node) -> Node:
    instance = node() if isinstance(node, type) else node
    if instance.type in _REGISTRY:
        raise RuntimeError(f"Node type already registered: {instance.type}")
    _REGISTRY[instance.type] = instance
    return instance


def get_node(node_type: str) -> Node:
    node = _REGISTRY.get(node_type)
    if node is None:
        raise KeyError(f"Unknown node type: {node_type}")
    return node


def all_nodes() -> dict[str, Node]:
    return dict(_REGISTRY)


def catalog() -> list[dict[str, Any]]:
    order = {"trigger": 0, "action": 1, "logic": 2, "ai": 3}
    entries = [node.catalog_entry() for node in _REGISTRY.values()]
    for entry in entries:
        entry["category_label"] = CATEGORY_LABELS.get(entry["category"], entry["category"])
    return sorted(entries, key=lambda item: (order.get(item["category"], 9), item["label"]))


def trigger_types() -> set[str]:
    return {node.type for node in _REGISTRY.values() if node.is_trigger}
