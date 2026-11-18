"""Base classes for the extensible node system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:  # pragma: no cover
    from app.services.executor.context import ExecutionContext


class NodeConfig(BaseModel):
    """Base configuration model for nodes.

    Extra keys are ignored so forward-compatible graphs and server-managed
    metadata (such as redacted webhook secrets) survive round-trips.
    """

    model_config = ConfigDict(extra="ignore")


@dataclass
class NodeResult:
    data: Any = None
    branch: str | None = None
    stop: bool = False
    message: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Node(ABC):
    type: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]
    category: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]
    outputs: ClassVar[list[str]] = ["default"]
    is_trigger: ClassVar[bool] = False
    dynamic_outputs: ClassVar[bool] = False

    @abstractmethod
    async def execute(
        self, ctx: "ExecutionContext", config: BaseModel, node: dict[str, Any]
    ) -> NodeResult:
        raise NotImplementedError

    def catalog_entry(self) -> dict[str, Any]:
        schema = self.config_model.model_json_schema()
        schema.pop("title", None)
        defaults: dict[str, Any] = {}
        for field_name, model_field in self.config_model.model_fields.items():
            if model_field.is_required():
                continue
            defaults[field_name] = model_field.get_default(call_default_factory=True)
        return {
            "type": self.type,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "outputs": self.outputs,
            "is_trigger": self.is_trigger,
            "dynamic_outputs": self.dynamic_outputs,
            "config_schema": schema,
            "defaults": defaults,
        }
