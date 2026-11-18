"""Logic nodes: conditions, switch, comparison, loops, delays and filters."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from app.core.errors import NodeExecutionError, ValidationError
from app.services.expressions import OPERATORS, evaluate_operator, resolve_value
from app.services.nodes.base import Node, NodeConfig, NodeResult
from app.services.nodes.registry import register

OPERATOR_CHOICES = sorted(OPERATORS)


class IfConfig(NodeConfig):
    left: Any = None
    operator: str = "eq"
    right: Any = None

    def conditions(self) -> tuple[Any, str, Any]:
        return self.left, self.operator, self.right


@register
class IfNode(Node):
    type = "logic_if"
    label = "Condição IF/ELSE"
    description = "Segue pelo caminho 'verdadeiro' ou 'falso' conforme a condição."
    category = "logic"
    outputs = ["true", "false"]
    config_model = IfConfig

    async def execute(self, ctx, config: IfConfig, node) -> NodeResult:
        left, operator, right = config.conditions()
        matched = evaluate_operator(
            operator,
            resolve_value(left, ctx.variables),
            resolve_value(right, ctx.variables),
        )
        return NodeResult(
            data={"result": matched, "branch": "true" if matched else "false"},
            branch="true" if matched else "false",
            message=f"Condição avaliada como {'verdadeira' if matched else 'falsa'}.",
        )


class SwitchCase(NodeConfig):
    id: str = Field(min_length=1, max_length=40)
    match: Any = None


class SwitchConfig(NodeConfig):
    value: Any = None
    cases: list[SwitchCase] = Field(default_factory=list, max_length=10)
    default_label: str = "default"


@register
class SwitchNode(Node):
    type = "logic_switch"
    label = "Switch"
    description = "Compara um valor com múltiplos casos e escolhe o caminho correspondente."
    category = "logic"
    outputs = ["default"]
    dynamic_outputs = True
    config_model = SwitchConfig

    async def execute(self, ctx, config: SwitchConfig, node) -> NodeResult:
        value = resolve_value(config.value, ctx.variables)
        for case in config.cases:
            if evaluate_operator("eq", value, resolve_value(case.match, ctx.variables)):
                return NodeResult(
                    data={"result": value, "branch": case.id},
                    branch=case.id,
                    message=f"Caso '{case.id}' selecionado.",
                )
        return NodeResult(
            data={"result": value, "branch": config.default_label},
            branch=config.default_label,
            message="Nenhum caso correspondeu; usando o caminho padrão.",
        )


class CompareConfig(NodeConfig):
    left: Any = None
    operator: str = "eq"
    right: Any = None


@register
class CompareNode(Node):
    type = "logic_compare"
    label = "Comparar valores"
    description = "Avalia uma comparação e devolve o resultado booleano sem ramificar."
    category = "logic"
    config_model = CompareConfig

    async def execute(self, ctx, config: CompareConfig, node) -> NodeResult:
        result = evaluate_operator(
            config.operator,
            resolve_value(config.left, ctx.variables),
            resolve_value(config.right, ctx.variables),
        )
        return NodeResult(data={"result": result}, message=f"Comparação: {result}.")


class FilterConfig(NodeConfig):
    left: Any = None
    operator: str = "is_not_empty"
    right: Any = None
    stop_on_false: bool = True


@register
class FilterNode(Node):
    type = "logic_filter"
    label = "Filtrar"
    description = "Permite ou interrompe o fluxo conforme uma condição."
    category = "logic"
    outputs = ["keep", "drop"]
    config_model = FilterConfig

    async def execute(self, ctx, config: FilterConfig, node) -> NodeResult:
        matched = evaluate_operator(
            config.operator,
            resolve_value(config.left, ctx.variables),
            resolve_value(config.right, ctx.variables),
        )
        branch = "keep" if matched else "drop"
        return NodeResult(
            data={"result": matched, "branch": branch},
            branch=branch,
            stop=config.stop_on_false and not matched,
            message="Item aprovado pelo filtro." if matched else "Item descartado pelo filtro.",
        )


class LoopConfig(NodeConfig):
    items: Any = None
    workflow_id: int | None = None
    max_iterations: int = Field(default=20, ge=1, le=100)
    continue_on_error: bool = True


@register
class LoopNode(Node):
    type = "logic_loop"
    label = "Loop"
    description = "Itera uma lista executando um sub-workflow para cada item e agrega resultados."
    category = "logic"
    config_model = LoopConfig

    async def execute(self, ctx, config: LoopConfig, node) -> NodeResult:
        if not config.workflow_id:
            raise ValidationError("O nó Loop exige um sub-workflow configurado.")

        raw_items = resolve_value(config.items, ctx.variables)
        if raw_items is None:
            raw_items = ctx.current_input
        if not isinstance(raw_items, (list, tuple)):
            if isinstance(raw_items, dict):
                raw_items = list(raw_items.items())
            else:
                raise NodeExecutionError("O nó Loop espera uma lista como entrada.")

        results: list[Any] = []
        failures: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items[: config.max_iterations]):
            try:
                result = await ctx.run_subflow(config.workflow_id, {"item": item, "index": index})
                results.append(result)
            except Exception as exc:
                failures.append({"index": index, "error": str(exc)})
                if not config.continue_on_error:
                    raise NodeExecutionError(
                        f"Loop interrompido na iteração {index}: {exc}"
                    ) from exc

        return NodeResult(
            data={
                "results": results,
                "count": len(results),
                "failures": failures,
                "truncated": len(raw_items) > config.max_iterations,
            },
            message=f"Loop concluído: {len(results)} iterações ({len(failures)} falhas).",
        )


class DelayConfig(NodeConfig):
    seconds: int = Field(default=1, ge=1, le=300)


@register
class DelayNode(Node):
    type = "logic_delay"
    label = "Atraso"
    description = "Pausa a execução por um número de segundos (máximo 300)."
    category = "logic"
    config_model = DelayConfig

    async def execute(self, ctx, config: DelayConfig, node) -> NodeResult:
        await asyncio.sleep(config.seconds)
        return NodeResult(data=ctx.current_input, message=f"Aguardou {config.seconds}s.")
