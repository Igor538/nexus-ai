"""Bounded AI agent loop with authorized tool execution."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.core.errors import NodeExecutionError

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

HTTP_REQUEST_TOOL: dict[str, Any] = {
    "name": "http_request",
    "description": (
        "Executa uma requisição HTTP para uma API pública. Use apenas quando necessário. "
        "Métodos permitidos: GET, POST, PUT, PATCH, DELETE. Destinos privados são bloqueados."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            "url": {"type": "string", "description": "URL http(s) pública."},
            "headers": {"type": "object", "description": "Cabeçalhos HTTP opcionais."},
            "body": {"type": "object", "description": "Corpo JSON opcional."},
        },
        "required": ["method", "url"],
    },
}


AVAILABLE_TOOLS = {"http_request": HTTP_REQUEST_TOOL}


async def run_agent(
    *,
    ctx,
    provider,
    model: str,
    system: str | None,
    goal: str,
    tools: list[str],
    max_iterations: int,
    temperature: float,
    execute_tool: ToolExecutor,
) -> dict[str, Any]:
    if not goal.strip():
        raise NodeExecutionError("O objetivo do agente está vazio.")

    iteration_cap = max(1, min(int(max_iterations), settings.ai_agent_max_iterations, 10))
    enabled_specs = [AVAILABLE_TOOLS[name] for name in tools if name in AVAILABLE_TOOLS]
    if not enabled_specs:
        enabled_specs = [HTTP_REQUEST_TOOL]

    messages: list[dict[str, Any]] = [{"role": "user", "content": goal}]
    trace: list[dict[str, Any]] = []
    answer: str | None = None
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for iteration in range(1, iteration_cap + 1):
        result = await ctx.ai_call(
            provider=provider,
            model=model,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=1024,
            tools=enabled_specs,
        )
        usage["prompt_tokens"] += result.prompt_tokens
        usage["completion_tokens"] += result.completion_tokens

        if not result.tool_calls:
            answer = result.content or ""
            trace.append({"iteration": iteration, "type": "answer", "content": answer[:2000]})
            break

        messages.append(
            {
                "role": "assistant",
                "content": result.content,
                "tool_calls": result.tool_calls,
            }
        )

        for call in result.tool_calls:
            if call["name"] not in AVAILABLE_TOOLS:
                tool_output = {"error": f"Ferramenta não autorizada: {call['name']}"}
            else:
                try:
                    tool_output = await execute_tool(call["name"], call.get("arguments") or {})
                except Exception as exc:
                    tool_output = {"error": str(exc)[:500]}

            serialized = json.dumps(tool_output, ensure_ascii=False, default=str)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": serialized[:8000],
                }
            )
            trace.append(
                {
                    "iteration": iteration,
                    "type": "tool_call",
                    "tool": call["name"],
                    "arguments": _redact_arguments(call.get("arguments") or {}),
                    "result_preview": serialized[:600],
                }
            )
    else:
        answer = None

    if answer is None:
        answer = "O agente atingiu o limite de iterações sem produzir uma resposta final."
        trace.append({"iteration": iteration_cap, "type": "limit_reached"})

    return {"answer": answer, "iterations": len(trace), "trace": trace, "usage": usage}


def _redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(arguments)
    headers = redacted.get("headers")
    if isinstance(headers, dict):
        redacted["headers"] = {
            key: ("***" if key.lower() in {"authorization", "x-api-key", "cookie"} else value)
            for key, value in headers.items()
        }
    return redacted
