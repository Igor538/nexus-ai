"""Workflow execution engine.

The engine interprets the workflow graph on the backend: it validates the graph,
resolves the trigger node, walks the DAG transferring data between nodes, handles
branching, retries, timeouts, cancellation and per-node logging.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.errors import AppError, ValidationError
from app.models.execution import ExecutionLog, WorkflowExecution
from app.models.workflow import Workflow
from app.schemas.workflow import NodeModel
from app.services.executor.context import ExecutionCancelled, ExecutionContext
from app.services.nodes import get_node
from app.services.workflow_service import validate_graph

logger = logging.getLogger(__name__)

TRIGGER_NODE_BY_KIND = {
    "manual": "trigger_manual",
    "webhook": "trigger_webhook",
    "schedule": "trigger_schedule",
    "event": "trigger_event",
}


class ExecutionError(RuntimeError):
    pass


@dataclass
class _LoadedExecution:
    id: int
    workflow_id: int
    user_id: int
    status: str
    trigger: str
    trigger_data: dict[str, Any]
    input: dict[str, Any]


@dataclass
class _LoadedWorkflow:
    id: int
    user_id: int
    graph: dict[str, Any]
    is_active: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def truncate_json(value: Any, max_bytes: int | None = None) -> Any:
    limit = max_bytes or settings.execution_max_output_bytes
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)[:limit]
    if len(text.encode("utf-8")) <= limit:
        return value
    return {"_truncated": True, "bytes": len(text.encode("utf-8")), "preview": text[:4000]}


def _merge_inputs(inputs: list[Any]) -> Any:
    dict_inputs = [item for item in inputs if isinstance(item, dict)]
    if len(dict_inputs) == len(inputs) and inputs:
        merged: dict[str, Any] = {}
        for item in dict_inputs:
            merged.update(item)
        return merged
    if len(inputs) == 1:
        return inputs[0]
    return inputs


class ExecutionEngine:
    def __init__(self, session_factory: Callable[[], Any] = SessionLocal) -> None:
        self.session_factory = session_factory

    async def run(self, execution_id: int) -> None:
        execution = self._load_execution(execution_id)
        if execution is None:
            logger.warning("execution_not_found", extra={"execution_id": execution_id})
            return
        if execution.status in {"success", "failed", "cancelled"}:
            return

        workflow = self._load_workflow(execution.workflow_id)
        if workflow is None:
            self._finalize(execution_id, "failed", error="Workflow não encontrado.")
            return

        graph = workflow.graph or {"nodes": [], "edges": []}
        db = self.session_factory()
        try:
            issues = validate_graph(
                db,
                user_id=workflow.user_id,
                graph=graph,
                is_active=workflow.is_active,
                workflow_id=workflow.id,
            )
        finally:
            db.close()
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            self._finalize(
                execution_id,
                "failed",
                error="Workflow inválido: " + "; ".join(issue["message"] for issue in errors[:3]),
            )
            return

        trigger_data = execution.trigger_data or {}
        start_node_id = self._resolve_start_node(
            graph, execution.trigger, trigger_data.get("node_id")
        )
        if not start_node_id:
            self._finalize(execution_id, "failed", error="Nenhum nó inicial compatível encontrado.")
            return

        self._update_execution(
            execution_id, status="running", started_at=_now(), finished_at=None, error=None
        )
        started = time.perf_counter()

        ctx = ExecutionContext(
            execution_id=execution_id,
            workflow_id=execution.workflow_id,
            user_id=execution.user_id,
            run_input=execution.input or {},
            trigger_data=trigger_data,
            trigger=execution.trigger,
            session_factory=self.session_factory,
        )
        ctx.subflow_runner = lambda workflow_id, payload: self._run_subflow(ctx, workflow_id, payload)

        try:
            result = await asyncio.wait_for(
                self._execute_graph(
                    graph=graph,
                    ctx=ctx,
                    start_node_id=start_node_id,
                    log_execution=True,
                ),
                timeout=settings.execution_timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._finalize(
                execution_id,
                "failed",
                error=f"Tempo limite de execução excedido ({settings.execution_timeout_seconds}s).",
                started=started,
            )
            return
        except ExecutionCancelled:
            self._finalize(execution_id, "cancelled", started=started)
            return
        except AppError as exc:
            self._finalize(execution_id, "failed", error=exc.message, started=started)
            return
        except ExecutionError as exc:
            self._finalize(execution_id, "failed", error=str(exc), started=started)
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("execution_crashed", extra={"execution_id": execution_id})
            self._finalize(
                execution_id, "failed", error=f"Erro interno na execução: {type(exc).__name__}", started=started
            )
            return

        self._finalize(
            execution_id,
            "success",
            output=truncate_json(result["output"]),
            steps=result["steps"],
            started=started,
        )

    async def _execute_graph(
        self,
        *,
        graph: dict[str, Any],
        ctx: ExecutionContext,
        start_node_id: str,
        log_execution: bool,
    ) -> dict[str, Any]:
        nodes: dict[str, NodeModel] = {}
        for raw_node in graph.get("nodes", []):
            node = NodeModel(**raw_node)
            nodes[node.id] = node
        edges = graph.get("edges", [])

        outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
        incoming: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
        order = {node_id: index for index, node_id in enumerate(nodes)}

        for edge in edges:
            source, target = edge.get("source"), edge.get("target")
            if source in nodes and target in nodes:
                outgoing[source].append(edge)
                incoming[target].append(edge)
        for edges_list in outgoing.values():
            edges_list.sort(key=lambda item: order.get(item["target"], 0))

        reachable = _reachable_nodes(start_node_id, outgoing)
        indegree = {
            node_id: len([edge for edge in incoming[node_id] if edge["source"] in reachable])
            for node_id in reachable
        }

        ready: deque[str] = deque([start_node_id])
        completed: set[str] = set()
        active_edges: set[str] = set()
        outputs: dict[str, Any] = {}
        last_data: Any = ctx.run_input
        steps = 0

        while ready:
            if steps >= settings.execution_max_steps:
                raise ExecutionError(
                    f"Limite de {settings.execution_max_steps} etapas por execução excedido."
                )
            await ctx.check_cancelled()
            node_id = ready.popleft()
            if node_id in completed:
                continue
            node = nodes[node_id]

            active_incoming = [
                edge for edge in incoming[node_id] if edge["id"] in active_edges
            ]
            if node_id != start_node_id and not active_incoming:
                completed.add(node_id)
                self._mark_skipped(ctx, node, log_execution)
                self._release_targets(
                    node_id, completed, incoming, outgoing, indegree, ready, reachable, order
                )
                continue

            if active_incoming:
                ctx.current_input = _merge_inputs([outputs.get(edge["source"]) for edge in active_incoming])
            else:
                ctx.current_input = ctx.run_input

            should_stop = False
            if node.disabled:
                result_data = ctx.current_input
                branch = None
                self._log_disabled(ctx, node, log_execution)
            else:
                try:
                    result = await self._execute_node(ctx, node, log_execution)
                except ExecutionCancelled:
                    raise
                except Exception as exc:
                    raise ExecutionError(self._describe_error(node, exc)) from exc
                result_data = result.data
                branch = result.branch
                should_stop = result.stop

            outputs[node_id] = result_data
            last_data = result_data
            completed.add(node_id)
            steps += 1
            ctx.variables["nodes"][node_id] = result_data

            if not should_stop:
                for edge in outgoing[node_id]:
                    handle = edge.get("sourceHandle")
                    if branch is None:
                        if handle in (None, "", "default"):
                            active_edges.add(edge["id"])
                    elif handle == branch:
                        active_edges.add(edge["id"])

            self._release_targets(
                node_id, completed, incoming, outgoing, indegree, ready, reachable, order
            )

        final_output = {
            "result": last_data,
            "nodes": {node_id: truncate_json(data, 32_768) for node_id, data in outputs.items()},
        }
        return {"output": final_output, "steps": steps}

    def _release_targets(
        self,
        node_id: str,
        completed: set[str],
        incoming: dict[str, list[dict[str, Any]]],
        outgoing: dict[str, list[dict[str, Any]]],
        indegree: dict[str, int],
        ready: deque[str],
        reachable: set[str],
        order: dict[str, int],
    ) -> None:
        targets = {edge["target"] for edge in outgoing.get(node_id, [])}
        for target in sorted(targets, key=lambda item: order.get(item, 0)):
            if target in completed:
                continue
            indegree[target] = indegree.get(target, 0) - 1
            all_done = all(
                edge["source"] in completed
                for edge in incoming.get(target, [])
                if edge["source"] in reachable
            )
            if indegree.get(target, 0) <= 0 and all_done and target not in ready:
                ready.append(target)

    async def _execute_node(self, ctx: ExecutionContext, node: NodeModel, log_execution: bool):
        implementation = get_node(node.type)
        try:
            config = implementation.config_model(**node.config)
        except Exception as exc:
            raise ValidationError(f"Configuração inválida do nó '{node.label or node.id}': {exc}") from exc

        attempts = max(1, min(node.retry_attempts, 5))
        delay = max(0.0, min(node.retry_delay_seconds, 30.0))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            log_id = self._start_log(ctx, node, attempt, log_execution)
            started = time.perf_counter()
            try:
                ctx.current_node_id = node.id
                result = await implementation.execute(ctx, config, node.model_dump())
                self._finish_log(
                    log_id,
                    status="success",
                    output=truncate_json(result.data, 8192),
                    message=result.message,
                    started=started,
                )
                return result
            except ExecutionCancelled:
                self._finish_log(log_id, status="cancelled", error="Execução cancelada.", started=started)
                raise
            except Exception as exc:
                last_error = exc
                self._finish_log(
                    log_id,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}"[:4000],
                    message=f"Tentativa {attempt} de {attempts} falhou.",
                    started=started,
                )
                if attempt < attempts:
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_error or ExecutionError("Falha desconhecida na execução do nó.")

    async def _run_subflow(self, parent: ExecutionContext, workflow_id: int, payload: dict[str, Any]) -> Any:
        db = self.session_factory()
        try:
            workflow = db.scalar(
                select(Workflow).where(
                    Workflow.id == workflow_id, Workflow.user_id == parent.user_id
                )
            )
        finally:
            db.close()
        if workflow is None:
            raise ValidationError("Sub-workflow não encontrado.")
        if parent.depth + 1 >= 3:
            raise ValidationError("Profundidade máxima de sub-workflows atingida.")

        graph = workflow.graph or {}
        start_node_id = self._resolve_start_node(graph, "subflow", None)
        if not start_node_id:
            raise ValidationError("O sub-workflow não possui um nó inicial compatível.")

        child = ExecutionContext(
            execution_id=None,
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            run_input=payload,
            trigger_data={},
            trigger="subflow",
            session_factory=self.session_factory,
            depth=parent.depth + 1,
        )
        child.subflow_runner = lambda wf_id, child_payload: self._run_subflow(child, wf_id, child_payload)
        result = await self._execute_graph(
            graph=graph, ctx=child, start_node_id=start_node_id, log_execution=False
        )
        return result["output"]["result"]

    def _resolve_start_node(
        self, graph: dict[str, Any], trigger: str, node_id: str | None
    ) -> str | None:
        nodes = graph.get("nodes", [])
        if node_id and any(node.get("id") == node_id for node in nodes):
            return node_id

        expected_type = TRIGGER_NODE_BY_KIND.get(trigger)
        candidates = [
            node for node in nodes if node.get("type") == expected_type and not node.get("disabled")
        ]
        if trigger in {"manual", "subflow"}:
            manual = [node for node in candidates if node.get("type") == "trigger_manual"]
            if manual:
                return manual[0]["id"]

        if candidates:
            return candidates[0]["id"]

        triggers = [
            node
            for node in nodes
            if str(node.get("type", "")).startswith("trigger_") and not node.get("disabled")
        ]
        if len(triggers) == 1:
            return triggers[0]["id"]
        return None

    # ------------------------------------------------------------------ logging

    def _start_log(
        self, ctx: ExecutionContext, node: NodeModel, attempt: int, log_execution: bool
    ) -> int | None:
        if not log_execution or not ctx.execution_id:
            return None
        db = self.session_factory()
        try:
            entry = ExecutionLog(
                execution_id=ctx.execution_id,
                node_id=node.id,
                node_type=node.type,
                node_name=node.label or node.id,
                status="running",
                attempt=attempt,
                input=truncate_json(ctx.current_input, 8192),
                started_at=_now(),
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry.id
        finally:
            db.close()

    def _finish_log(
        self,
        log_id: int | None,
        *,
        status: str,
        output: Any = None,
        error: str | None = None,
        message: str | None = None,
        started: float | None = None,
    ) -> None:
        if log_id is None:
            return
        db = self.session_factory()
        try:
            entry = db.get(ExecutionLog, log_id)
            if entry is None:
                return
            entry.status = status
            entry.output = output
            entry.error = error
            entry.message = message
            entry.finished_at = _now()
            if started is not None:
                entry.duration_ms = int((time.perf_counter() - started) * 1000)
            db.commit()
        finally:
            db.close()

    def _mark_skipped(self, ctx: ExecutionContext, node: NodeModel, log_execution: bool) -> None:
        if not log_execution or not ctx.execution_id:
            return
        db = self.session_factory()
        try:
            db.add(
                ExecutionLog(
                    execution_id=ctx.execution_id,
                    node_id=node.id,
                    node_type=node.type,
                    node_name=node.label or node.id,
                    status="skipped",
                    attempt=1,
                    message="Nó ignorado: nenhum ramo ativo chegou até ele.",
                    started_at=_now(),
                    finished_at=_now(),
                    duration_ms=0,
                )
            )
            db.commit()
        finally:
            db.close()

    def _log_disabled(self, ctx: ExecutionContext, node: NodeModel, log_execution: bool) -> None:
        if not log_execution or not ctx.execution_id:
            return
        db = self.session_factory()
        try:
            db.add(
                ExecutionLog(
                    execution_id=ctx.execution_id,
                    node_id=node.id,
                    node_type=node.type,
                    node_name=node.label or node.id,
                    status="skipped",
                    attempt=1,
                    message="Nó desativado: os dados passaram direto.",
                    started_at=_now(),
                    finished_at=_now(),
                    duration_ms=0,
                )
            )
            db.commit()
        finally:
            db.close()

    # --------------------------------------------------------------- persistence

    def _load_execution(self, execution_id: int) -> _LoadedExecution | None:
        db = self.session_factory()
        try:
            execution = db.get(WorkflowExecution, execution_id)
            if execution is None:
                return None
            return _LoadedExecution(
                id=execution.id,
                workflow_id=execution.workflow_id,
                user_id=execution.user_id,
                status=execution.status,
                trigger=execution.trigger,
                trigger_data=dict(execution.trigger_data or {}),
                input=dict(execution.input or {}),
            )
        finally:
            db.close()

    def _load_workflow(self, workflow_id: int) -> _LoadedWorkflow | None:
        db = self.session_factory()
        try:
            workflow = db.get(Workflow, workflow_id)
            if workflow is None:
                return None
            return _LoadedWorkflow(
                id=workflow.id,
                user_id=workflow.user_id,
                graph=workflow.graph,
                is_active=workflow.is_active,
            )
        finally:
            db.close()

    def _update_execution(self, execution_id: int, **fields: Any) -> None:
        db = self.session_factory()
        try:
            execution = db.get(WorkflowExecution, execution_id)
            if execution is None:
                return
            for key, value in fields.items():
                setattr(execution, key, value)
            db.commit()
        finally:
            db.close()

    def _finalize(
        self,
        execution_id: int,
        status: str,
        *,
        output: Any = None,
        error: str | None = None,
        steps: int | None = None,
        started: float | None = None,
    ) -> None:
        db = self.session_factory()
        try:
            execution = db.get(WorkflowExecution, execution_id)
            if execution is None:
                return
            if execution.status == "cancelled":
                status = "cancelled"
            execution.status = status
            execution.finished_at = _now()
            if started is not None:
                execution.duration_ms = int((time.perf_counter() - started) * 1000)
            elif execution.started_at:
                execution.duration_ms = int(
                    (execution.finished_at - execution.started_at).total_seconds() * 1000
                )
            if output is not None:
                execution.output = output
            if error is not None:
                execution.error = error[:4000]
            if steps is not None:
                execution.steps = steps
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _describe_error(node: NodeModel, exc: Exception) -> str:
        label = node.label or node.id
        if isinstance(exc, AppError):
            return f"Nó '{label}' falhou: {exc.message}"
        return f"Nó '{label}' falhou: {type(exc).__name__}: {exc}"[:2000]


def _reachable_nodes(start: str, outgoing: dict[str, list[dict[str, Any]]]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(edge["target"] for edge in outgoing.get(current, []))
    return seen

