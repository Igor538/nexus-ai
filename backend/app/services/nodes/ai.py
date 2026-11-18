"""AI nodes: chat, prompt templates, agents, classification, extraction, summary."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import Field

from app.core.errors import NodeExecutionError, ValidationError
from app.services.ai.agent import run_agent
from app.services.expressions import resolve_value
from app.services.nodes.base import Node, NodeConfig, NodeResult
from app.services.nodes.registry import register

PROVIDERS = ["", "openai", "gemini"]


class AIBaseConfig(NodeConfig):
    provider: Literal["", "openai", "gemini", "groq", "openrouter", "ollama"] = ""
    model: str = Field(default="", max_length=120)
    credential_id: int | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


class PromptTemplateConfig(NodeConfig):
    template: str = Field(default="", max_length=20_000)
    variables: dict[str, Any] = Field(default_factory=dict)


@register
class PromptTemplateNode(Node):
    type = "ai_prompt"
    label = "Prompt Template"
    description = "Monta um prompt a partir de um template com variáveis do fluxo (sem chamar IA)."
    category = "ai"
    config_model = PromptTemplateConfig

    async def execute(self, ctx, config: PromptTemplateConfig, node) -> NodeResult:
        variables = {**ctx.variables, **resolve_value(config.variables, ctx.variables)}
        prompt = resolve_value(config.template, variables)
        if not isinstance(prompt, str) or not prompt.strip():
            raise NodeExecutionError("O template de prompt está vazio.")
        return NodeResult(data={"prompt": prompt}, message="Prompt montado.", meta={"chars": len(prompt)})


class ChatConfig(AIBaseConfig):
    system: str = Field(default="", max_length=20_000)
    prompt: str = Field(default="{{ input }}", max_length=20_000)


@register
class ChatModelNode(Node):
    type = "ai_chat"
    label = "Chat Model"
    description = "Envia um prompt para um modelo de IA e devolve a resposta em texto."
    category = "ai"
    config_model = ChatConfig

    async def execute(self, ctx, config: ChatConfig, node) -> NodeResult:
        prompt = resolve_value(config.prompt, ctx.variables)
        system = resolve_value(config.system, ctx.variables) or None
        if not prompt:
            raise NodeExecutionError("O prompt do modelo de chat está vazio.")

        result = await ctx.ai_chat(
            provider=config.provider,
            model=config.model,
            credential_id=config.credential_id,
            system=system,
            messages=[{"role": "user", "content": str(prompt)}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        if not result.content:
            raise NodeExecutionError("O modelo não retornou conteúdo.")
        return NodeResult(
            data={
                "text": result.content,
                "provider": result.provider,
                "model": result.model,
                "usage": {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                },
            },
            message=f"Resposta gerada por {result.provider}/{result.model}.",
        )


class AgentConfig(AIBaseConfig):
    system: str = Field(default="", max_length=20_000)
    goal: str = Field(default="", max_length=20_000)
    tools: list[Literal["http_request"]] = Field(default_factory=lambda: ["http_request"])
    max_iterations: int = Field(default=5, ge=1, le=10)


@register
class AIAgentNode(Node):
    type = "ai_agent"
    label = "AI Agent"
    description = (
        "Agente com tool calling: raciocina, chama ferramentas autorizadas e produz uma resposta final."
    )
    category = "ai"
    config_model = AgentConfig

    async def execute(self, ctx, config: AgentConfig, node) -> NodeResult:
        goal = resolve_value(config.goal, ctx.variables)
        system = resolve_value(config.system, ctx.variables) or (
            "Você é um agente de automação. Use as ferramentas disponíveis apenas quando "
            "necessário e nunca invente resultados. Responda em português."
        )
        if not goal:
            raise NodeExecutionError("O objetivo do agente está vazio.")

        provider = ctx.resolve_provider(config.provider)
        model = ctx.resolve_model(provider, config.model)

        async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            if name != "http_request":
                raise NodeExecutionError(f"Ferramenta não autorizada: {name}")
            method = str(arguments.get("method", "GET")).upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                raise NodeExecutionError("Método HTTP não permitido pelo agente.")
            url = str(arguments.get("url", ""))
            headers = arguments.get("headers") or {}
            body = arguments.get("body")
            response = await ctx.http_request(
                method=method,
                url=url,
                headers=headers if isinstance(headers, dict) else {},
                json_body=body,
                allow_private_networks=False,
            )
            return {
                "status_code": response.status_code,
                "body": response.body,
                "url": response.url,
                "truncated": len(response.text) >= 1_000_000,
            }

        output = await run_agent(
            ctx=ctx,
            provider=provider,
            model=model,
            system=system,
            goal=str(goal),
            tools=list(config.tools),
            max_iterations=config.max_iterations,
            temperature=config.temperature,
            execute_tool=execute_tool,
        )
        return NodeResult(
            data=output,
            message=f"Agente concluiu em {output['iterations']} passo(s).",
        )


class ClassifyConfig(AIBaseConfig):
    text: str = Field(default="{{ input }}", max_length=20_000)
    labels: list[str] = Field(min_length=2, max_length=20)


@register
class ClassifyTextNode(Node):
    type = "ai_classify"
    label = "Classificar texto"
    description = "Classifica um texto em uma das categorias informadas usando IA."
    category = "ai"
    config_model = ClassifyConfig

    async def execute(self, ctx, config: ClassifyConfig, node) -> NodeResult:
        text = resolve_value(config.text, ctx.variables)
        if not text:
            raise NodeExecutionError("Texto para classificação está vazio.")
        labels = [label.strip() for label in config.labels if label.strip()]
        if len(labels) < 2:
            raise ValidationError("Informe pelo menos duas categorias distintas.")

        result = await ctx.ai_chat(
            provider=config.provider,
            model=config.model,
            credential_id=config.credential_id,
            system="Classificador de texto. Responda somente JSON válido, sem markdown.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Classifique o texto em exatamente uma destas categorias: {labels}.\n"
                        'Formato: {"label": "<categoria>", "confidence": 0.0, "reason": "<curto>"}\n\n'
                        f"Texto:\n{text}"
                    ),
                }
            ],
            temperature=0,
            max_tokens=256,
        )
        parsed = _extract_json(result.content or "")
        label = str(parsed.get("label", "")).strip()
        if label not in labels:
            raise NodeExecutionError(f"O modelo retornou uma categoria inválida: {label!r}")
        confidence = parsed.get("confidence", 0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        return NodeResult(
            data={
                "label": label,
                "confidence": confidence,
                "reason": str(parsed.get("reason", ""))[:500],
                "provider": result.provider,
                "model": result.model,
            },
            message=f"Texto classificado como '{label}'.",
        )


class ExtractionField(NodeConfig):
    name: str = Field(min_length=1, max_length=60)
    type: Literal["string", "number", "boolean", "array", "object"] = "string"
    description: str = Field(default="", max_length=300)


class ExtractConfig(AIBaseConfig):
    text: str = Field(default="{{ input }}", max_length=30_000)
    fields: list[ExtractionField] = Field(min_length=1, max_length=25)


@register
class ExtractInformationNode(Node):
    type = "ai_extract"
    label = "Extrair informações"
    description = "Extrai campos estruturados de um texto, com validação de tipos."
    category = "ai"
    config_model = ExtractConfig

    async def execute(self, ctx, config: ExtractConfig, node) -> NodeResult:
        text = resolve_value(config.text, ctx.variables)
        if not text:
            raise NodeExecutionError("Texto para extração está vazio.")

        field_specs = [
            {"name": field.name, "type": field.type, "description": field.description}
            for field in config.fields
        ]
        result = await ctx.ai_chat(
            provider=config.provider,
            model=config.model,
            credential_id=config.credential_id,
            system="Extrator de dados. Responda somente JSON válido, sem markdown.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extraia os campos abaixo do texto. Use null quando não encontrado.\n"
                        f"Campos: {json.dumps(field_specs, ensure_ascii=False)}\n"
                        'Formato: {"data": {<campos>}}\n\n'
                        f"Texto:\n{text}"
                    ),
                }
            ],
            temperature=0,
            max_tokens=1024,
        )
        parsed = _extract_json(result.content or "")
        data = parsed.get("data") if isinstance(parsed, dict) else None
        if not isinstance(data, dict):
            raise NodeExecutionError("A IA não retornou um objeto JSON válido.")

        cleaned: dict[str, Any] = {}
        invalid: list[str] = []
        for field in config.fields:
            value = data.get(field.name)
            if value is not None and not _type_matches(value, field.type):
                invalid.append(field.name)
                value = None
            cleaned[field.name] = value

        return NodeResult(
            data={
                "data": cleaned,
                "missing": [name for name, value in cleaned.items() if value is None],
                "invalid_fields": invalid,
                "provider": result.provider,
                "model": result.model,
            },
            message="Extração concluída." if not invalid else f"Extração com tipos inválidos: {invalid}",
        )


class SummaryConfig(AIBaseConfig):
    text: str = Field(default="{{ input }}", max_length=60_000)
    max_words: int = Field(default=120, ge=20, le=1000)
    style: Literal["neutro", "executivo", "bullet points", "tecnico"] = "neutro"


@register
class SummarizeNode(Node):
    type = "ai_summarize"
    label = "Resumir conteúdo"
    description = "Gera um resumo objetivo de um texto longo."
    category = "ai"
    config_model = SummaryConfig

    async def execute(self, ctx, config: SummaryConfig, node) -> NodeResult:
        text = resolve_value(config.text, ctx.variables)
        if not text:
            raise NodeExecutionError("Texto para resumo está vazio.")

        result = await ctx.ai_chat(
            provider=config.provider,
            model=config.model,
            credential_id=config.credential_id,
            system="Você resume conteúdo com precisão e sem inventar informações.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Resuma o texto em no máximo {config.max_words} palavras no estilo "
                        f"'{config.style}'. Responda em português.\n\nTexto:\n{text}"
                    ),
                }
            ],
            temperature=0.2,
            max_tokens=max(256, config.max_words * 3),
        )
        summary = (result.content or "").strip()
        if not summary:
            raise NodeExecutionError("A IA não retornou um resumo.")
        return NodeResult(
            data={
                "summary": summary,
                "word_count": len(summary.split()),
                "provider": result.provider,
                "model": result.model,
            },
            message="Resumo gerado.",
        )


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise NodeExecutionError("A resposta da IA não contém JSON válido.")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise NodeExecutionError(f"JSON inválido retornado pela IA: {exc}") from exc
    if not isinstance(parsed, dict):
        raise NodeExecutionError("A IA retornou JSON que não é um objeto.")
    return parsed


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True
