from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: str | None
    node_type: str | None
    node_name: str | None
    status: str
    attempt: int
    message: str | None
    error: str | None
    input: Any | None
    output: Any | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    user_id: int
    status: str
    trigger: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    steps: int
    created_at: datetime
    workflow_name: str | None = None


class ExecutionDetailResponse(ExecutionResponse):
    trigger_data: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    output: Any | None = None
    logs: list[ExecutionLogResponse] = Field(default_factory=list)


class WorkflowRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    trigger_node_id: str | None = None
