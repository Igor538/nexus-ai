from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CredentialCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: str = Field(min_length=2, max_length=40)
    data: dict[str, Any]


class CredentialUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    data: dict[str, Any] | None = None


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
