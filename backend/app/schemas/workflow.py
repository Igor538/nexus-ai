from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Position(BaseModel):
    x: float = 0
    y: float = 0


class NodeModel(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-.]+$")
    type: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=150)
    position: Position = Field(default_factory=Position)
    config: dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False
    retry_attempts: int = Field(default=1, ge=1, le=5)
    retry_delay_seconds: float = Field(default=1.0, ge=0, le=30)

    @field_validator("config")
    @classmethod
    def config_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(repr(value)) > 200_000:
            raise ValueError("Configuração do nó excede o tamanho máximo.")
        return value


class EdgeModel(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    sourceHandle: str | None = Field(default=None, max_length=64)
    targetHandle: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=80)


class Graph(BaseModel):
    nodes: list[NodeModel] = Field(default_factory=list, max_length=100)
    edges: list[EdgeModel] = Field(default_factory=list, max_length=300)
    viewport: dict[str, float] | None = None


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    graph: Graph | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    graph: Graph | None = None


class WorkflowDuplicateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool
    version: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    edge_count: int = 0
    trigger_types: list[str] = Field(default_factory=list)


class WorkflowResponse(WorkflowSummary):
    graph: Graph
    webhook_url: str | None = None
    schedule_cron: str | None = None


class WorkflowValidationIssue(BaseModel):
    severity: str = "error"
    node_id: str | None = None
    message: str


class WorkflowValidationResponse(BaseModel):
    valid: bool
    issues: list[WorkflowValidationIssue]


class WorkflowVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    version: int
    name: str
    description: str | None
    origin: str
    created_by: int | None
    created_at: datetime
    node_count: int = 0
    edge_count: int = 0


class WorkflowVersionDetail(WorkflowVersionSummary):
    graph: Graph
