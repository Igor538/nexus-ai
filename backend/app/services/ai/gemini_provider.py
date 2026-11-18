"""Google Gemini (Generative Language API) provider."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.services.ai.base import AIProvider, AIProviderError, ChatResult

_TYPE_MAP = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


class GeminiProvider(AIProvider):
    name = "gemini"

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        api_key: str,
    ) -> ChatResult:
        if not api_key:
            raise AIProviderError("Chave de API do Gemini não configurada.")

        payload: dict[str, Any] = {
            "contents": _to_gemini_contents(messages),
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": to_gemini_schema(
                                tool.get("parameters", {"type": "object", "properties": {}})
                            ),
                        }
                        for tool in tools
                    ]
                }
            ]

        model_name = model if model.startswith("models/") else f"models/{model}"
        url = f"{settings.gemini_base_url.rstrip('/')}/{model_name}:generateContent"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Falha de rede ao chamar o Gemini: {exc.__class__.__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("error", {}).get("message", ""))[:300]
            except Exception:
                detail = response.text[:300]
            raise AIProviderError(f"Gemini respondeu {response.status_code}: {detail}")

        try:
            body = response.json()
            candidate = body["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIProviderError("Resposta inesperada do Gemini.") from exc

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for part in candidate:
            if "text" in part:
                text_parts.append(part["text"])
            if "functionCall" in part:
                call = part["functionCall"]
                tool_calls.append(
                    {
                        "id": f"call_{len(tool_calls)}",
                        "name": call.get("name", ""),
                        "arguments": call.get("args") or {},
                    }
                )

        usage = body.get("usageMetadata") or {}
        return ChatResult(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            model=model,
            provider=self.name,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            latency_ms=latency_ms,
        )


def _to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "user":
            contents.append({"role": "user", "parts": [{"text": message.get("content") or ""}]})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            if message.get("content"):
                parts.append({"text": message["content"]})
            for call in message.get("tool_calls") or []:
                parts.append({"functionCall": {"name": call["name"], "args": call.get("arguments") or {}}})
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message.get("name") or "tool",
                                "response": {"result": _parse_tool_content(message.get("content"))},
                            }
                        }
                    ],
                }
            )
    return contents


def _parse_tool_content(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a JSON Schema subset to Gemini's OpenAPI-like schema."""
    result: dict[str, Any] = {}
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "string")
    if schema_type in _TYPE_MAP:
        result["type"] = _TYPE_MAP[schema_type]
    elif "properties" in schema:
        result["type"] = "OBJECT"
    else:
        result["type"] = "STRING"

    if schema.get("description"):
        result["description"] = schema["description"]
    if schema.get("enum"):
        result["enum"] = [str(item) for item in schema["enum"]]

    if result["type"] == "OBJECT":
        properties = schema.get("properties") or {}
        result["properties"] = {name: to_gemini_schema(value) for name, value in properties.items()}
        if schema.get("required"):
            result["required"] = schema["required"]
    if result["type"] == "ARRAY":
        result["items"] = to_gemini_schema(schema.get("items") or {"type": "string"})
    return result
