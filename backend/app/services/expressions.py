"""Safe template resolution and condition evaluation for workflow data flow.

Templates use ``{{ expression }}`` where the expression is a dotted path into the
execution context (``input.customer.email``, ``nodes.node_1.body.items.0``).
No arbitrary Python or Jinja evaluation is performed.
"""

from __future__ import annotations

import json
import re
from typing import Any

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
FULL_TEMPLATE = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")

OPERATORS = {
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_empty",
    "is_not_empty",
    "regex",
    "in",
    "not_in",
    "truthy",
    "falsy",
}


class ExpressionError(ValueError):
    pass


def resolve_path(path: str, variables: dict[str, Any]) -> Any:
    """Resolve a dotted path, returning None when any segment is missing."""
    current: Any = variables
    for raw_segment in path.split("."):
        segment = raw_segment.strip()
        if not segment:
            continue
        if isinstance(current, dict):
            if segment in current:
                current = current[segment]
                continue
            return None
        if isinstance(current, (list, tuple)):
            try:
                index = int(segment)
            except ValueError:
                return None
            if -len(current) <= index < len(current):
                current = current[index]
                continue
            return None
        return None
    return current


def render_string(template: str, variables: dict[str, Any]) -> Any:
    full = FULL_TEMPLATE.match(template)
    if full:
        return resolve_path(full.group(1), variables)

    def replace(match: re.Match[str]) -> str:
        value = resolve_path(match.group(1), variables)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return TEMPLATE_PATTERN.sub(replace, template)


def resolve_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_string(value, variables)
    if isinstance(value, list):
        return [resolve_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: resolve_value(item, variables) for key, item in value.items()}
    return value


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def evaluate_operator(operator: str, left: Any, right: Any = None) -> bool:
    operator = (operator or "eq").strip().lower()
    if operator not in OPERATORS:
        raise ExpressionError(f"Operador desconhecido: {operator}")

    if operator == "truthy":
        return bool(left)
    if operator == "falsy":
        return not bool(left)
    if operator == "is_empty":
        return left in (None, "", [], {})
    if operator == "is_not_empty":
        return left not in (None, "", [], {})

    if operator in {"eq", "neq"}:
        equal = left == right
        if not equal:
            left_num, right_num = _coerce_number(left), _coerce_number(right)
            if left_num is not None and right_num is not None:
                equal = left_num == right_num
            elif isinstance(left, str) and isinstance(right, str):
                equal = left.strip() == right.strip()
        return equal if operator == "eq" else not equal

    if operator in {"gt", "gte", "lt", "lte"}:
        left_num, right_num = _coerce_number(left), _coerce_number(right)
        if left_num is None or right_num is None:
            raise ExpressionError("Comparações de ordem exigem valores numéricos.")
        if operator == "gt":
            return left_num > right_num
        if operator == "gte":
            return left_num >= right_num
        if operator == "lt":
            return left_num < right_num
        return left_num <= right_num

    left_text, right_text = _as_text(left), _as_text(right)

    if operator == "contains":
        if isinstance(left, (list, tuple, dict)):
            return right in left
        return right_text.lower() in left_text.lower()
    if operator == "not_contains":
        if isinstance(left, (list, tuple, dict)):
            return right not in left
        return right_text.lower() not in left_text.lower()
    if operator == "starts_with":
        return left_text.lower().startswith(right_text.lower())
    if operator == "ends_with":
        return left_text.lower().endswith(right_text.lower())
    if operator == "regex":
        try:
            return re.search(right_text, left_text) is not None
        except re.error as exc:
            raise ExpressionError(f"Expressão regular inválida: {exc}") from exc
    if operator == "in":
        if isinstance(right, (list, tuple, dict)):
            return left in right
        return left_text in right_text
    if operator == "not_in":
        if isinstance(right, (list, tuple, dict)):
            return left not in right
        return left_text not in right_text
    return False
