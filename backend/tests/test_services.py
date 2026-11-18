"""Service-level tests: expressions, SSRF policy, AI registry and schedules."""

from __future__ import annotations

import pytest
from conftest import API

from app.core.errors import ValidationError
from app.core.http import validate_outbound_url
from app.services.ai.registry import (
    available_providers,
    estimate_cost,
    get_provider,
    resolve_model,
)
from app.services.expressions import evaluate_operator, resolve_path, resolve_value


def test_expression_resolution():
    variables = {
        "input": {"cliente": {"nome": "Ana"}, "itens": [{"qtd": 2}, {"qtd": 5}]},
        "nodes": {"node_1": {"total": 7}},
    }
    assert resolve_path("input.cliente.nome", variables) == "Ana"
    assert resolve_path("input.itens.1.qtd", variables) == 5
    assert resolve_path("input.ausente", variables) is None
    assert resolve_value("{{ input.cliente.nome }}", variables) == "Ana"
    assert resolve_value("Olá {{ input.cliente.nome }}!", variables) == "Olá Ana!"
    assert resolve_value({"total": "{{ nodes.node_1.total }}"}, variables) == {"total": 7}

    assert evaluate_operator("eq", 1, 1)
    assert evaluate_operator("gt", 5, 3)
    assert evaluate_operator("contains", "nexus ai", "nexus")
    assert evaluate_operator("is_empty", "")
    assert not evaluate_operator("falsy", "valor")


def test_ssrf_policy_blocks_internal_destinations():
    for url in (
        "http://localhost:8000",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "http://10.0.0.5/",
    ):
        with pytest.raises(ValidationError):
            validate_outbound_url(url)

    assert validate_outbound_url("https://93.184.216.34/path") == (
        "https://93.184.216.34/path"
    )


def test_ai_registry_defaults_and_pricing():
    providers = {item["name"]: item for item in available_providers()}
    assert "gemini" in providers
    assert "groq" in providers
    assert "openrouter" in providers
    assert "ollama" in providers
    assert providers["gemini"]["is_default"] is True
    assert providers["ollama"]["requires_api_key"] is False
    assert providers["gemini"]["requires_api_key"] is True

    assert get_provider("gemini").name == "gemini"
    assert get_provider(None).name == "gemini"
    assert resolve_model("gemini", None) == "gemini-2.0-flash"
    assert resolve_model("groq", None)
    assert estimate_cost("gemini-2.0-flash", 1000, 1000) >= 0

    with pytest.raises(ValidationError):
        get_provider("inexistente")


def test_schedule_trigger_syncs_upcoming(client, user, make_workflow):
    graph = {
        "nodes": [
            {
                "id": "cron",
                "type": "trigger_schedule",
                "config": {"cron": "*/5 * * * *", "timezone": "America/Sao_Paulo"},
            }
        ],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    workflow = make_workflow(graph=graph, name="Fluxo agendado")
    assert workflow["schedule_cron"] == "*/5 * * * *"

    dashboard = client.get(f"{API}/dashboard/stats", headers=user["headers"])
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["workflows"]["total"] >= 1
    assert any(
        item["workflow_id"] == workflow["id"]
        for item in payload["upcoming_schedules"]
    )

