"""Node package: importing modules registers every node type."""

from app.services.nodes import actions, ai, logic, triggers  # noqa: F401  (registration side effects)
from app.services.nodes.base import Node, NodeConfig, NodeResult
from app.services.nodes.registry import all_nodes, catalog, get_node, trigger_types

__all__ = [
    "Node",
    "NodeConfig",
    "NodeResult",
    "all_nodes",
    "catalog",
    "get_node",
    "trigger_types",
]
