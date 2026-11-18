"""Execution context handed to every node during a run."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import NodeExecutionError
from app.core.http import HttpResponse, safe_http_request
from app.models.execution import WorkflowExecution
from app.models.notification import Notification
from app.services.ai.base import AIProvider, ChatResult
from app.services.ai.registry import get_provider, resolve_api_key, resolve_model
from app.services.ai.usage import check_daily_quota, record_usage
from app.services.credentials import resolve_credential_data

SubflowRunner = Callable[[int, dict[str, Any]], Awaitable[Any]]


class ExecutionCancelled(Exception):
    pass


@dataclass
class ExecutionContext:
    execution_id: int | None
    workflow_id: int
    user_id: int
    run_input: dict[str, Any]
    trigger_data: dict[str, Any]
    trigger: str
    session_factory: Callable[[], Any]
    current_input: Any = None
    variables: dict[str, Any] = field(default_factory=dict)
    depth: int = 0
    subflow_runner: SubflowRunner | None = None
    log_sink: Callable[[str, dict[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        self.variables.setdefault("input", self.run_input or {})
        self.variables.setdefault("trigger", self.trigger_data or {})
        self.variables.setdefault("nodes", {})

    def resolve(self, template: str) -> Any:
        from app.services.expressions import resolve_value

        return resolve_value(template, self.variables)

    def add_log(self, message: str, **extra: Any) -> None:
        if self.log_sink:
            self.log_sink(message, extra)

    async def check_cancelled(self) -> None:
        if not self.execution_id:
            return
        db = self.session_factory()
        try:
            status = db.scalar(
                select(WorkflowExecution.status).where(WorkflowExecution.id == self.execution_id)
            )
        finally:
            db.close()
        if status == "cancelled":
            raise ExecutionCancelled("Execução cancelada pelo usuário.")

    async def http_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        content: bytes | str | None = None,
        timeout_seconds: float | None = None,
        allow_private_networks: bool | None = None,
    ) -> HttpResponse:
        return await safe_http_request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json_body=json_body,
            data=data,
            content=content,
            timeout_seconds=timeout_seconds,
            allow_private_networks=allow_private_networks,
        )

    async def build_auth_headers(
        self, *, credential_id: int | None, auth_type: str, header_name: str = "X-API-Key"
    ) -> dict[str, str]:
        import base64

        if auth_type == "none":
            return {}
        if not credential_id:
            raise NodeExecutionError("Selecione uma credencial para usar autenticação.")

        db = self.session_factory()
        try:
            if auth_type == "bearer":
                data = resolve_credential_data(
                    db, user_id=self.user_id, credential_id=credential_id, expected_type="http_bearer"
                )
                return {"Authorization": f"Bearer {data['token']}"}
            if auth_type == "basic":
                data = resolve_credential_data(
                    db, user_id=self.user_id, credential_id=credential_id, expected_type="http_basic"
                )
                raw = f"{data['username']}:{data['password']}".encode("utf-8")
                return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
            if auth_type == "header":
                data = resolve_credential_data(
                    db, user_id=self.user_id, credential_id=credential_id, expected_type="api_key"
                )
                return {header_name or "X-API-Key": data["api_key"]}
        finally:
            db.close()
        return {}

    async def create_notification(self, *, title: str, body: str, level: str = "info") -> int:
        db = self.session_factory()
        try:
            notification = Notification(
                user_id=self.user_id,
                execution_id=self.execution_id,
                title=title[:200],
                body=body[:4000],
                level=level,
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)
            return notification.id
        finally:
            db.close()

    async def send_discord_message(self, *, credential_id: int | None, content: str) -> tuple[bool, int]:
        if not credential_id:
            raise NodeExecutionError("Selecione uma credencial de webhook do Discord.")
        db = self.session_factory()
        try:
            data = resolve_credential_data(
                db, user_id=self.user_id, credential_id=credential_id, expected_type="discord_webhook"
            )
        finally:
            db.close()
        response = await self.http_request(
            method="POST",
            url=data["url"],
            json_body={"content": content[:1900]},
            timeout_seconds=15,
            allow_private_networks=False,
        )
        return 200 <= response.status_code < 300, response.status_code

    async def send_telegram_message(self, *, credential_id: int | None, text: str) -> tuple[bool, int]:
        if not credential_id:
            raise NodeExecutionError("Selecione uma credencial de bot do Telegram.")
        db = self.session_factory()
        try:
            data = resolve_credential_data(
                db, user_id=self.user_id, credential_id=credential_id, expected_type="telegram_bot"
            )
        finally:
            db.close()
        token = data["bot_token"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = await self.http_request(
            method="POST",
            url=url,
            json_body={"chat_id": data["chat_id"], "text": text[:4000]},
            timeout_seconds=15,
            allow_private_networks=False,
        )
        return 200 <= response.status_code < 300, response.status_code

    def resolve_provider(self, provider: str | None) -> str:
        return (provider or settings.ai_default_provider).strip().lower()

    def resolve_model(self, provider_name: str, model: str | None) -> str:
        return resolve_model(provider_name, model)

    def _api_key(self, provider_name: str, credential_id: int | None) -> str:
        if credential_id:
            db = self.session_factory()
            try:
                data = resolve_credential_data(
                    db, user_id=self.user_id, credential_id=credential_id, expected_type="api_key"
                )
                return data["api_key"]
            finally:
                db.close()
        return resolve_api_key(provider_name)

    async def ai_chat(
        self,
        *,
        provider: str | None,
        model: str | None,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        credential_id: int | None = None,
    ) -> ChatResult:
        provider_name = self.resolve_provider(provider)
        provider_obj = get_provider(provider_name)
        resolved_model = self.resolve_model(provider_name, model)
        api_key = self._api_key(provider_name, credential_id)
        return await self.ai_call(
            provider=provider_obj,
            model=resolved_model,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            api_key=api_key,
        )

    async def ai_call(
        self,
        *,
        provider: AIProvider,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        api_key: str | None = None,
    ) -> ChatResult:
        key = api_key if api_key is not None else resolve_api_key(provider.name)
        if not key and provider.name != "ollama":
            raise NodeExecutionError(
                f"Nenhuma chave de API configurada para o provedor '{provider.name}'. "
                "Configure a variável de ambiente correspondente ou uma credencial do tipo Chave de API."
            )

        db = self.session_factory()
        try:
            check_daily_quota(db, self.user_id)
        finally:
            db.close()

        result = await provider.chat(
            model=model,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            api_key=key,
        )

        db = self.session_factory()
        try:
            record_usage(
                db,
                user_id=self.user_id,
                provider=result.provider or provider.name,
                model=result.model or model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                workflow_id=self.workflow_id,
                execution_id=self.execution_id,
                node_id=(self.current_node_id if hasattr(self, "current_node_id") else None),
                latency_ms=result.latency_ms,
            )
        finally:
            db.close()

        return result

    async def run_subflow(self, workflow_id: int, payload: dict[str, Any]) -> Any:
        if self.depth >= 3:
            raise NodeExecutionError("Profundidade máxima de sub-workflows atingida (3).")
        if self.subflow_runner is None:
            raise NodeExecutionError("Sub-workflows não estão disponíveis neste contexto.")
        await asyncio.sleep(0)
        return await self.subflow_runner(workflow_id, payload)

    current_node_id: str | None = None
