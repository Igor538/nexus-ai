"""Tests for AI-assisted workflow generation."""

from __future__ import annotations

import json

import pytest

from app.core.errors import ValidationError
from app.services.ai import generator
from app.services.ai.base import AIProviderError, ChatResult

API = "/api/v1"


class FakeProvider:
    name = "fake"

    def __init__(self, content: str | None) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def chat(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        return ChatResult(
            content=self.content,
            model=kwargs["model"],
            provider=self.name,
            prompt_tokens=10,
            completion_tokens=20,
        )


def graph_payload() -> str:
    return json.dumps(
        {
            "nodes": [
                {
                    "id": "hook",
                    "type": "trigger_webhook",
                    "label": "Entrada",
                    "config": {"method": "POST", "secret": "should-be-dropped"},
                },
                {
                    "id": "hook",
                    "type": "action_notification",
                    "label": "Avisar",
                    "config": {
                        "channel": "internal",
                        "title": "Novo lead",
                        "message": "Recebido {{ input }}",
                    },
                },
                {"id": "ghost", "type": "not_a_real_node", "config": {}},
            ],
            "edges": [
                {"source": "hook", "target": "hook", "sourceHandle": "default"},
                {"source": "ghost", "target": "hook"},
                {"source": "unknown", "target": "hook"},
            ],
            "explanation": "Recebe um lead e notifica o time.",
        }
    )


@pytest.mark.asyncio
async def test_generate_normalizes_graph(db_session, user, monkeypatch):
    monkeypatch.setattr(generator, "resolve_api_key", lambda name: "test-key")
    fake = FakeProvider(f"```json\n{graph_payload()}\n```")

    result = await generator.generate_workflow_graph(
        db_session,
        user_id=user["id"],
        prompt="Receba leads por webhook e me notifique",
        provider_name="gemini",
        provider=fake,
    )

    graph = result["graph"]
    assert [node["type"] for node in graph["nodes"]] == [
        "trigger_webhook",
        "action_notification",
    ]
    assert graph["nodes"][0]["id"] != graph["nodes"][1]["id"]
    assert graph["nodes"][0]["config"]["secret_configured"] is False
    assert "secret" not in graph["nodes"][0]["config"]
    assert graph["edges"] == []
    assert all("position" in node for node in graph["nodes"])
    assert result["explanation"] == "Recebe um lead e notifica o time."
    assert result["provider"] == "fake"
    assert fake.calls and "Catálogo de nós" in fake.calls[0]["messages"][0]["content"]
    assert isinstance(result["issues"], list)


@pytest.mark.asyncio
async def test_generate_requires_api_key(db_session, user, monkeypatch):
    monkeypatch.setattr(generator, "resolve_api_key", lambda name: "")
    with pytest.raises(ValidationError):
        await generator.generate_workflow_graph(
            db_session,
            user_id=user["id"],
            prompt="Fluxo simples",
            provider_name="openai",
            provider=FakeProvider("{}"),
        )


@pytest.mark.asyncio
async def test_generate_reports_provider_errors(db_session, user, monkeypatch):
    class BrokenProvider(FakeProvider):
        async def chat(self, **kwargs) -> ChatResult:
            raise AIProviderError("limite atingido")

    monkeypatch.setattr(generator, "resolve_api_key", lambda name: "test-key")
    with pytest.raises(ValidationError, match="limite atingido"):
        await generator.generate_workflow_graph(
            db_session,
            user_id=user["id"],
            prompt="Fluxo simples",
            provider_name="gemini",
            provider=BrokenProvider(None),
        )


def test_extract_json_rejects_garbage():
    with pytest.raises(ValidationError):
        generator.extract_json("desculpe, não consigo ajudar")
    with pytest.raises(ValidationError):
        generator.extract_json("")
    assert generator.extract_json('{"nodes": []}') == {"nodes": []}


def test_generate_endpoint(client, user, monkeypatch):
    async def fake_generate(db, **kwargs):
        return {
            "graph": {
                "nodes": [
                    {
                        "id": "trigger_1",
                        "type": "trigger_manual",
                        "label": "Manual",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    }
                ],
                "edges": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
            "issues": [
                {"severity": "warning", "node_id": None, "message": "Fluxo curto."}
            ],
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "provider_label": "Google Gemini (free tier)",
            "explanation": "Um gatilho manual.",
        }

    monkeypatch.setattr("app.api.workflows.generate_workflow_graph", fake_generate)
    response = client.post(
        f"{API}/workflows/generate",
        json={"prompt": "Crie um fluxo manual"},
        headers=user["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["graph"]["nodes"][0]["type"] == "trigger_manual"
    assert body["issues"][0]["severity"] == "warning"
    assert body["provider"] == "gemini"

    anonymous = client.post(f"{API}/workflows/generate", json={"prompt": "Fluxo"})
    assert anonymous.status_code == 401
