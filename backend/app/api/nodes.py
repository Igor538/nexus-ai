"""Node catalog for the visual editor."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.services.nodes.registry import CATEGORY_LABELS, catalog

router = APIRouter()


@router.get("")
def list_nodes(current_user: User = Depends(get_current_user)):
    categories: dict[str, dict[str, str]] = {}
    nodes = catalog()
    for entry in nodes:
        category = entry["category"]
        categories[category] = {
            "key": category,
            "label": CATEGORY_LABELS.get(category, category),
        }
    return {
        "nodes": nodes,
        "categories": list(categories.values()),
    }
