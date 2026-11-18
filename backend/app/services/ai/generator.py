"""AI-assisted workflow graph generation.

The model only proposes a graph; the server validates node types, sanitizes
identifiers, lays the graph out and reuses the regular validation pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.registry import (
    PROVIDER_LABELS,
    available_providers,
    get_provider,
    resolve_api_key,
    resolve_model,
)
from app.services.ai.usage import check_daily_quota, record_usage
from app.services.nodes import all_nodes
from app.services.workflow_service import validate_graph

MAX_GENERATED_NODES = 25
MAX_GENERATED_EDGES = 60
ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-.]+$")

SYSTEM_PROMPT = (
    "Você projeta automações para o Nexus AI. Responda SOMENTE com um objeto JSON válido, "
    "sem markdown e sem comentários, no formato "
    '{"nodes":[{"id":"...","type":"...","label":"...","config":{}}],'
    '"edges":[{"source":"...","target":"...","sourceHandle":"default"}],'
    '"explanation":"..."}. '
    "Use apenas tipos da lista fornecida. Configure cada nó com os campos do catálogo, "
    "respeitando tipos e valores padrão. Crie exatamente um nó de gatilho, encadeie os nós "
    "em um fluxo acíclico começando pelo gatilho e use sourceHandle \"default\" exceto em nós "
    "com portas nomeadas (logic_if: true/false; logic_switch: ids dos casos). "
    "Ids curtos em minúsculas com letras, números, underscore ou hífen. Não invente segredos."
)


def catalog_prompt() -> str:
    """Compact catalog: only what the model needs to choose nodes and configs."""
    entries: list[dict[str, Any]] = []
    for node in all_nodes().values():
        entry = node.catalog_entry()
        schema = entry.get("config_schema") or {}
        properties = schema.get("properties") or {}
        defaults = entry.get("defaults") or {}
        fields: dict[str, Any] = {}
        for name, spec in properties.items():
            if name in {"secret", "secret_encrypted", "secret_hash", "secret_configured"}:
                continue
            item: dict[str, Any] = {"type": (spec or {}).get("type", "string")}
            if name in defaults:
                item["default"] = defaults[name]
            fields[name] = item
        entries.append(
            {
                "type": entry["type"],
                "label": entry["label"],
                "category": entry["category"],
                "is_trigger": entry["is_trigger"],
                "outputs": entry["outputs"],
                "description": entry["description"],
                "fields": fields,
            }
        )
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def build_messages(prompt: str) -> list[dict[str, Any]]:
    content = (
        f"Objetivo do usuário: {prompt.strip()}\n\n"
        f"Catálogo de nós (JSON): {catalog_prompt()}\n\n"
        "Regras: entre 3 e 12 nós; exatamente um gatilho; sem ciclos; "
        "conexões sempre entre ids existentes; configurações completas e válidas. "
        "Explique o fluxo em no máximo duas frases no campo explanation."
    )
    return [{"role": "user", "content": content}]


async def generate_workflow_graph(
    db: Session,
    *,
    user_id: int,
    prompt: str,
    provider_name: str | None = None,
    model: str | None = None,
    provider: AIProvider | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    goal = (prompt or "").strip()
    if len(goal) < 3:
        raise ValidationError("Descreva a automação desejada com pelo menos 3 caracteres.")

    name = (provider_name or settings.ai_default_provider or "gemini").strip().lower()
    known = {item["name"] for item in available_providers()}
    if name not in known:
        raise ValidationError(f"Provedor de IA desconhecido: {name}.")
    provider_obj = provider or get_provider(name)
    resolved_model = resolve_model(name, model)
    key = api_key if api_key is not None else resolve_api_key(name)
    if not key and name != "ollama":
        raise ValidationError(
            f"Nenhuma chave de API configurada para o provedor '{name}'. "
            "Configure a variável de ambiente correspondente ou use uma credencial de IA.",
            details={"provider": name},
        )

    check_daily_quota(db, user_id)
    try:
        result = await provider_obj.chat(
            model=resolved_model,
            messages=build_messages(goal),
            system=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=3000,
            api_key=key,
        )
    except AIProviderError as exc:
        raise ValidationError(f"Falha no provedor de IA: {exc}") from exc

    record_usage(
        db,
        user_id=user_id,
        provider=result.provider or name,
        model=result.model or resolved_model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
    )

    payload = extract_json(result.content)
    graph = normalize_generated_graph(payload)
    issues = validate_graph(
        db,
        user_id=user_id,
        graph=graph,
        is_active=False,
        workflow_id=None,
    )
    explanation = payload.get("explanation")
    return {
        "graph": graph,
        "issues": issues,
        "provider": result.provider or name,
        "model": result.model or resolved_model,
        "provider_label": PROVIDER_LABELS.get(name, name),
        "explanation": explanation[:600] if isinstance(explanation, str) else None,
    }


def extract_json(content: str | None) -> dict[str, Any]:
    if not content or not content.strip():
        raise ValidationError("O provedor de IA não retornou conteúdo.")
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValidationError("A resposta da IA não contém um objeto JSON.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValidationError(f"A resposta da IA não é um JSON válido: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ValidationError("A resposta da IA precisa ser um objeto JSON.")
    return payload


def normalize_generated_graph(payload: dict[str, Any]) -> dict[str, Any]:
    registry = all_nodes()
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValidationError("A IA não gerou nenhum nó válido.")

    used_ids: set[str] = set()
    id_map: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    for index, item in enumerate(raw_nodes, start=1):
        if len(nodes) >= MAX_GENERATED_NODES:
            break
        if not isinstance(item, dict):
            continue
        node_type = str(item.get("type") or "").strip()
        implementation = registry.get(node_type)
        if implementation is None:
            continue
        original_id = item.get("id")
        node_id = _unique_id(original_id, used_ids, fallback=f"node_{index}")
        if isinstance(original_id, str) and original_id and original_id not in id_map:
            id_map[original_id] = node_id
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        config = {
            key: value
            for key, value in config.items()
            if key not in {"secret_encrypted", "secret_hash", "secret_configured"}
        }
        if node_type in {"trigger_webhook", "trigger_event"}:
            config.pop("secret", None)
            config.pop("secret_configured", None)
            config["secret_configured"] = False
        label = item.get("label")
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "label": (
                    str(label).strip()[:150]
                    if isinstance(label, str) and label.strip()
                    else implementation.label
                ),
                "position": {"x": 0, "y": 0},
                "config": config,
                "disabled": bool(item.get("disabled")) if isinstance(item.get("disabled"), bool) else False,
                "retry_attempts": 1,
                "retry_delay_seconds": 1.0,
            }
        )

    if not nodes:
        raise ValidationError("A IA não gerou nenhum nó com tipo reconhecido.")

    valid_ids = {node["id"] for node in nodes}
    edges: list[dict[str, Any]] = []
    seen_edge_ids: set[str] = set()
    seen_pairs: set[tuple[str, str, str]] = set()
    raw_edges = raw_edges if isinstance(raw_edges, list) else []
    for item in raw_edges:
        if len(edges) >= MAX_GENERATED_EDGES:
            break
        if not isinstance(item, dict):
            continue
        source = _map_endpoint(item.get("source"), id_map, valid_ids)
        target = _map_endpoint(item.get("target"), id_map, valid_ids)
        if source is None or target is None or source == target:
            continue
        handle = item.get("sourceHandle")
        handle = handle if isinstance(handle, str) and handle.strip() else "default"
        handle = handle.strip()[:64]
        pair = (source, target, handle)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edge_id = str(item.get("id") or "").strip()
        if not edge_id or edge_id in seen_edge_ids or not ID_PATTERN.match(edge_id):
            edge_id = _unique_id(f"edge_{len(edges) + 1}", seen_edge_ids, fallback="edge")
        seen_edge_ids.add(edge_id)
        edges.append(
            {
                "id": edge_id[:64],
                "source": source,
                "target": target,
                "sourceHandle": handle,
                "targetHandle": None,
                "label": None,
            }
        )

    _layout(nodes, edges)
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 1}}


def _unique_id(candidate: Any, used: set[str], *, fallback: str) -> str:
    base = candidate.strip()[:64] if isinstance(candidate, str) else ""
    if not base or not ID_PATTERN.match(base):
        base = fallback
    value = base
    suffix = 2
    while value in used:
        value = f"{base}_{suffix}"[:64]
        suffix += 1
    used.add(value)
    return value


def _map_endpoint(value: Any, id_map: dict[str, str], valid_ids: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    mapped = id_map.get(value, value)
    return mapped if mapped in valid_ids else None


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    incoming = {node["id"]: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node["id"]: [] for node in nodes}
    for edge in edges:
        source, target = edge["source"], edge["target"]
        outgoing[source].append(target)
        incoming[target] += 1

    levels: dict[str, int] = {}
    queue = [node_id for node_id, count in incoming.items() if count == 0]
    for node_id in queue:
        levels[node_id] = 0
    order = list(queue)
    while order:
        current = order.pop(0)
        level = levels.get(current, 0)
        for neighbor in outgoing.get(current, []):
            if neighbor in levels:
                continue
            levels[neighbor] = level + 1
            order.append(neighbor)
    for node in nodes:
        levels.setdefault(node["id"], 0)

    by_level: dict[int, list[str]] = {}
    for node in nodes:
        by_level.setdefault(levels[node["id"]], []).append(node["id"])
    positions = {
        node_id: {"x": 60 + level * 270, "y": 60 + index * 150}
        for level, ids in by_level.items()
        for index, node_id in enumerate(ids)
    }
    for node in nodes:
        node["position"] = positions[node["id"]]
