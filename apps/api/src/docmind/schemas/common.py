from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Paged(ApiModel):
    total: int
    limit: int
    offset: int


class Ok(ApiModel):
    ok: bool = True
