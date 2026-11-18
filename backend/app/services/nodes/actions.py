"""Action nodes: HTTP requests, data shaping, text/JSON transforms and notifications."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Literal

from pydantic import Field, field_validator

from app.core.errors import NodeExecutionError, ValidationError
from app.services.expressions import resolve_value
from app.services.nodes.base import Node, NodeConfig, NodeResult
from app.services.nodes.registry import register

HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]


class HttpRequestConfig(NodeConfig):
    method: str = "GET"
    url: str = Field(min_length=1, max_length=2048)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    body_type: Literal["none", "json", "text", "form"] = "none"
    body: Any = None
    credential_id: int | None = None
    auth_type: Literal["none", "bearer", "basic", "header"] = "none"
    auth_header_name: str = "X-API-Key"
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    fail_on_error: bool = True

    @field_validator("method")
    @classmethod
    def method_valid(cls, value: str) -> str:
        value = value.upper()
        if value not in HTTP_METHODS:
            raise ValueError("Método HTTP inválido.")
        return value


@register
class HttpRequestNode(Node):
    type = "action_http"
    label = "Requisição HTTP"
    description = "Chama uma API externa com proteção contra SSRF e limites de resposta."
    category = "action"
    config_model = HttpRequestConfig

    async def execute(self, ctx, config: HttpRequestConfig, node) -> NodeResult:
        variables = ctx.variables
        url = resolve_value(config.url, variables)
        if not isinstance(url, str) or not url.strip():
            raise NodeExecutionError("A URL da requisição está vazia após a resolução de variáveis.")

        headers = {
            str(key): str(value)
            for key, value in resolve_value(config.headers, variables).items()
            if value is not None
        }
        query = resolve_value(config.query, variables)
        body = resolve_value(config.body, variables)

        auth_headers = await ctx.build_auth_headers(
            credential_id=config.credential_id,
            auth_type=config.auth_type,
            header_name=config.auth_header_name,
        )
        headers.update(auth_headers)

        payload: dict[str, Any] = {}
        if config.body_type == "json" and body is not None:
            payload["json_body"] = body
        elif config.body_type == "text" and body is not None:
            payload["content"] = str(body)
        elif config.body_type == "form" and body is not None:
            payload["data"] = body

        response = await ctx.http_request(
            method=config.method,
            url=url,
            headers=headers,
            params=query,
            timeout_seconds=config.timeout_seconds,
            **payload,
        )

        result = {
            "status_code": response.status_code,
            "headers": {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {"set-cookie", "authorization", "proxy-authenticate"}
            },
            "body": response.body,
            "url": response.url,
            "elapsed_ms": response.elapsed_ms,
        }

        if config.fail_on_error and response.status_code >= 400:
            raise NodeExecutionError(
                f"A requisição HTTP retornou status {response.status_code}.",
                details={"status_code": response.status_code, "url": response.url},
            )

        return NodeResult(data=result, message=f"HTTP {response.status_code} em {response.elapsed_ms}ms")


class SetDataConfig(NodeConfig):
    fields: dict[str, Any] = Field(default_factory=dict)
    merge_with_input: bool = True


@register
class SetDataNode(Node):
    type = "action_set_data"
    label = "Definir dados"
    description = "Monta um novo objeto de dados a partir de variáveis e valores fixos."
    category = "action"
    config_model = SetDataConfig

    async def execute(self, ctx, config: SetDataConfig, node) -> NodeResult:
        resolved = resolve_value(config.fields, ctx.variables)
        if config.merge_with_input and isinstance(ctx.current_input, dict):
            merged = {**ctx.current_input, **resolved}
            return NodeResult(data=merged, message="Dados combinados com a entrada.")
        return NodeResult(data=resolved, message="Dados definidos.")


class TextTransformConfig(NodeConfig):
    operation: Literal[
        "trim",
        "uppercase",
        "lowercase",
        "capitalize",
        "reverse",
        "length",
        "replace",
        "split",
        "join",
        "regex_extract",
        "slugify",
        "template",
    ] = "trim"
    input: Any = None
    find: str = ""
    replace_with: str = ""
    separator: str = ","
    pattern: str = ""
    group: int = 0
    template: str = "{{ input }}"


@register
class TextTransformNode(Node):
    type = "action_text"
    label = "Transformar texto"
    description = "Aplica operações de texto (limpeza, substituição, divisão, regex, template)."
    category = "action"
    config_model = TextTransformConfig

    async def execute(self, ctx, config: TextTransformConfig, node) -> NodeResult:
        raw = config.input if config.input not in (None, "") else ctx.current_input
        raw = resolve_value(raw, ctx.variables)
        text = "" if raw is None else (raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False))

        op = config.operation
        if op == "trim":
            value: Any = text.strip()
        elif op == "uppercase":
            value = text.upper()
        elif op == "lowercase":
            value = text.lower()
        elif op == "capitalize":
            value = text[:1].upper() + text[1:]
        elif op == "reverse":
            value = text[::-1]
        elif op == "length":
            value = len(text)
        elif op == "replace":
            value = text.replace(config.find, config.replace_with)
        elif op == "split":
            value = [part for part in text.split(config.separator)] if config.separator else list(text)
        elif op == "join":
            items = raw if isinstance(raw, list) else [text]
            value = config.separator.join(str(item) for item in items)
        elif op == "regex_extract":
            if not config.pattern:
                raise ValidationError("O nó de texto exige um padrão regex.")
            try:
                match = re.search(config.pattern, text)
            except re.error as exc:
                raise NodeExecutionError(f"Regex inválido: {exc}") from exc
            if not match:
                raise NodeExecutionError("Nenhuma correspondência encontrada para o padrão regex.")
            try:
                value = match.group(config.group)
            except IndexError as exc:
                raise NodeExecutionError("Grupo de captura inexistente.") from exc
        elif op == "slugify":
            normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
            value = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
        elif op == "template":
            value = resolve_value(config.template, ctx.variables)
        else:  # pragma: no cover - guarded by Literal
            raise ValidationError("Operação de texto desconhecida.")

        return NodeResult(
            data={"result": value, "text": value if isinstance(value, str) else None},
            message=f"Texto processado ({op}).",
        )


class JsonTransformConfig(NodeConfig):
    operation: Literal["parse", "stringify", "get", "pick", "merge", "set"] = "get"
    input: Any = None
    path: str = ""
    value: Any = None
    keys: list[str] = Field(default_factory=list)
    merge: dict[str, Any] = Field(default_factory=dict)


@register
class JsonTransformNode(Node):
    type = "action_json"
    label = "Manipular JSON"
    description = "Lê, converte, filtra e combina objetos JSON."
    category = "action"
    config_model = JsonTransformConfig

    async def execute(self, ctx, config: JsonTransformConfig, node) -> NodeResult:
        raw = resolve_value(config.input, ctx.variables) if config.input not in (None, "") else ctx.current_input
        op = config.operation
        result: Any

        if op == "parse":
            if isinstance(raw, str):
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise NodeExecutionError(f"JSON inválido: {exc}") from exc
            else:
                result = raw
        elif op == "stringify":
            result = json.dumps(raw, ensure_ascii=False)
        elif op == "get":
            result = _dig(raw, config.path)
        elif op == "pick":
            if not isinstance(raw, dict):
                raise NodeExecutionError("A operação 'pick' exige um objeto JSON.")
            result = {key: raw.get(key) for key in config.keys}
        elif op == "merge":
            base = raw if isinstance(raw, dict) else {}
            result = {**base, **resolve_value(config.merge, ctx.variables)}
        elif op == "set":
            if not isinstance(raw, dict):
                raise NodeExecutionError("A operação 'set' exige um objeto JSON.")
            result = dict(raw)
            _set_path(result, config.path, resolve_value(config.value, ctx.variables))
        else:  # pragma: no cover
            raise ValidationError("Operação JSON desconhecida.")

        return NodeResult(data={"result": result}, message=f"JSON processado ({op}).")


class NotificationConfig(NodeConfig):
    channel: Literal["internal", "discord", "telegram"] = "internal"
    title: str = Field(default="Notificação do Nexus AI", max_length=200)
    message: str = Field(default="", max_length=4000)
    credential_id: int | None = None
    level: Literal["info", "success", "warning", "error"] = "info"


@register
class NotificationNode(Node):
    type = "action_notification"
    label = "Enviar notificação"
    description = "Cria uma notificação interna ou envia mensagem ao Discord/Telegram."
    category = "action"
    config_model = NotificationConfig

    async def execute(self, ctx, config: NotificationConfig, node) -> NodeResult:
        title = str(resolve_value(config.title, ctx.variables))
        message = str(resolve_value(config.message, ctx.variables))

        if config.channel == "internal":
            notification_id = await ctx.create_notification(title=title, body=message, level=config.level)
            return NodeResult(
                data={"channel": "internal", "delivered": True, "notification_id": notification_id},
                message="Notificação interna criada.",
            )

        if config.channel == "discord":
            delivered, status = await ctx.send_discord_message(
                credential_id=config.credential_id, content=f"**{title}**\n{message}"
            )
        else:
            delivered, status = await ctx.send_telegram_message(
                credential_id=config.credential_id, text=f"{title}\n\n{message}"
            )

        if not delivered:
            raise NodeExecutionError(f"Falha ao enviar notificação ({config.channel}).")
        return NodeResult(
            data={"channel": config.channel, "delivered": True, "status_code": status},
            message=f"Notificação enviada via {config.channel}.",
        )


def _dig(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _set_path(target: dict, path: str, value: Any) -> None:
    segments = [segment for segment in path.split(".") if segment]
    if not segments:
        raise NodeExecutionError("Informe um caminho para definir o valor.")
    current = target
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[segments[-1]] = value
