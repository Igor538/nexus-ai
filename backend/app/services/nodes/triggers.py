"""Trigger nodes: manual runs, webhooks, schedules and external events."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from app.services.nodes.base import Node, NodeConfig, NodeResult
from app.services.nodes.registry import register


class ManualTriggerConfig(NodeConfig):
    pass


@register
class ManualTrigger(Node):
    type = "trigger_manual"
    label = "Execução manual"
    description = "Inicia o fluxo quando alguém clica em executar ou chama a API de execução."
    category = "trigger"
    is_trigger = True
    config_model = ManualTriggerConfig

    async def execute(self, ctx, config, node) -> NodeResult:
        return NodeResult(
            data=ctx.variables.get("input") or {}, message="Fluxo iniciado manualmente."
        )


class WebhookTriggerConfig(NodeConfig):
    method: str = "POST"
    secret: str | None = None
    require_signature: bool = False

    @field_validator("method")
    @classmethod
    def method_valid(cls, value: str) -> str:
        value = value.upper()
        if value not in {"POST", "PUT", "PATCH"}:
            raise ValueError("Método de webhook deve ser POST, PUT ou PATCH.")
        return value


@register
class WebhookTrigger(Node):
    type = "trigger_webhook"
    label = "Webhook"
    description = "Recebe uma requisição HTTP externa autenticada e inicia o fluxo."
    category = "trigger"
    is_trigger = True
    config_model = WebhookTriggerConfig

    async def execute(self, ctx, config, node) -> NodeResult:
        payload = ctx.trigger_data.get("body")
        return NodeResult(
            data={
                "body": payload,
                "headers": ctx.trigger_data.get("headers", {}),
                "query": ctx.trigger_data.get("query", {}),
            },
            message="Webhook recebido.",
        )


class ScheduleTriggerConfig(NodeConfig):
    cron: str = Field(default="0 9 * * *", min_length=5, max_length=120)
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def cron_valid(cls, value: str) -> str:
        from croniter import croniter

        if not croniter.is_valid(value):
            raise ValueError("Expressão cron inválida.")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Fuso horário inválido.") from exc
        return value


@register
class ScheduleTrigger(Node):
    type = "trigger_schedule"
    label = "Agendamento"
    description = "Executa o fluxo em uma agenda cron (o agendador verifica a cada 30 segundos)."
    category = "trigger"
    is_trigger = True
    config_model = ScheduleTriggerConfig

    async def execute(self, ctx, config, node) -> NodeResult:
        return NodeResult(
            data={
                "scheduled": True,
                "cron": config.cron,
                "timezone": config.timezone,
                "scheduled_at": ctx.trigger_data.get("scheduled_at"),
            },
            message="Fluxo iniciado pelo agendamento.",
        )


class EventTriggerConfig(NodeConfig):
    topic: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.\-]+$")
    secret: str | None = None


@register
class EventTrigger(Node):
    type = "trigger_event"
    label = "Evento externo"
    description = "Inicia o fluxo quando um evento nomeado é publicado no endpoint de eventos."
    category = "trigger"
    is_trigger = True
    config_model = EventTriggerConfig

    async def execute(self, ctx, config, node) -> NodeResult:
        return NodeResult(
            data={
                "topic": config.topic,
                "payload": ctx.trigger_data.get("body") or {},
                "headers": ctx.trigger_data.get("headers", {}),
            },
            message=f"Evento '{config.topic}' recebido.",
        )
