"""OpenAI-compatible Chat Completions provider (OpenAI, Groq, OpenRouter, Ollama)."""

from __future__ import annotations

import json
import time
from typing import Any, ClassVar

import httpx

from app.core.config import settings
from app.services.ai.base import AIProvider, AIProviderError, ChatResult


class OpenAICompatibleProvider(AIProvider):
    name: ClassVar[str] = "openai"
    label: ClassVar[str] = "OpenAI"
    base_url_setting: ClassVar[str] = "openai_base_url"
    api_key_setting: ClassVar[str] = "openai_api_key"
    requires_api_key: ClassVar[bool] = True
    extra_headers: ClassVar[dict[str, str]] = {}
    key_error: ClassVar[str] = "Chave de API da OpenAI não configurada."

    @property
    def base_url(self) -> str:
        return str(getattr(settings, self.base_url_setting)).rstrip("/")

    def resolve_api_key(self, explicit_key: str | None) -> str:
        return explicit_key or (getattr(settings, self.api_key_setting, "") or "")

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        api_key: str | None = None,
    ) -> ChatResult:
        resolved_key = self.resolve_api_key(api_key)
        if self.requires_api_key and not resolved_key:
            raise AIProviderError(self.key_error)

        payload: dict[str, Any] = {
            "model": model,
            "messages": _to_openai_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
                for tool in tools
            ]

        headers = {"Content-Type": "application/json", **self.extra_headers}
        if resolved_key:
            headers["Authorization"] = f"Bearer {resolved_key}"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(
                f"Falha de rede ao chamar {self.label}: {exc.__class__.__name__}"
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = str(body.get("error", {}).get("message", ""))[:300]
            except Exception:
                detail = response.text[:300]
            raise AIProviderError(f"{self.label} respondeu {response.status_code}: {detail}")

        try:
            body = response.json()
            choice = body["choices"][0]["message"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"Resposta inesperada de {self.label}.") from exc

        tool_calls = []
        for call in choice.get("tool_calls") or []:
            function = call.get("function", {})
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw": function.get("arguments")}
            tool_calls.append(
                {
                    "id": call.get("id") or f"call_{len(tool_calls)}",
                    "name": function.get("name", ""),
                    "arguments": arguments,
                }
            )

        usage = body.get("usage") or {}
        return ChatResult(
            content=choice.get("content"),
            tool_calls=tool_calls,
            model=body.get("model", model),
            provider=self.name,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
        )


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    label = "OpenAI"


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    label = "Groq"
    base_url_setting = "groq_base_url"
    api_key_setting = "groq_api_key"
    key_error = "Chave de API da Groq não configurada (GROQ_API_KEY)."


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    label = "OpenRouter"
    base_url_setting = "openrouter_base_url"
    api_key_setting = "openrouter_api_key"
    key_error = "Chave de API do OpenRouter não configurada (OPENROUTER_API_KEY)."
    extra_headers = {
        "HTTP-Referer": "https://github.com/Igor538/nexus-ai",
        "X-Title": "Nexus AI",
    }


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"
    label = "Ollama (local)"
    base_url_setting = "ollama_base_url"
    api_key_setting = "ollama_api_key"  # never required
    requires_api_key = False
    key_error = ""


def _to_openai_messages(messages: list[dict[str, Any]], system: str | None) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    if system:
        payload.append({"role": "system", "content": system})
    for message in messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            payload.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(
                                    call.get("arguments") or {}, ensure_ascii=False
                                ),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            payload.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id", ""),
                    "content": message.get("content") or "",
                }
            )
        else:
            payload.append({"role": role, "content": message.get("content") or ""})
    return payload
