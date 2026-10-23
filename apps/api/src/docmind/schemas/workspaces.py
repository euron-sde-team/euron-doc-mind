from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from docmind.schemas.common import ApiModel


class WorkspaceSettings(ApiModel):
    """Per-workspace retrieval and answering preferences."""

    answer_mode: Literal["auto", "extractive"] = Field(
        default="auto",
        description="auto uses the configured model if any; extractive never calls a model.",
    )
    top_k: int = Field(default=6, ge=1, le=12, description="Passages given to the answerer.")
    context_token_budget: int | None = Field(default=None, ge=200, le=32000)
    chunk_tokens: int | None = Field(default=None, ge=64, le=2048)
    chunk_overlap_tokens: int | None = Field(default=None, ge=0, le=512)
    cache_enabled: bool = True


class WorkspaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class WorkspaceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    settings: WorkspaceSettings | None = None


class WorkspaceOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    settings: WorkspaceSettings
    corpus_version: int
    role: str
    created_at: datetime


class MemberOut(ApiModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: str
    joined_at: datetime


class MemberAdd(ApiModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=120)
    role: Literal["owner", "editor", "viewer"] = "viewer"


class MemberAdded(ApiModel):
    member: MemberOut
    temporary_password: str | None = Field(
        default=None, description="Set only when the account was created by this call. Shown once."
    )


class MemberUpdate(ApiModel):
    role: Literal["owner", "editor", "viewer"]
