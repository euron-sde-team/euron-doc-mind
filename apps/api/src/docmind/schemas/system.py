from __future__ import annotations

from docmind.schemas.common import ApiModel


class GeneratorInfo(ApiModel):
    label: str
    provider: str
    model: str | None
    uses_model: bool


class SystemInfo(ApiModel):
    product_name: str
    version: str
    generator: GeneratorInfo
    embeddings: str
    embedding_dim: int
    tokenizer: str
    max_upload_mb: int
    accepted_extensions: list[str]
    allow_signup: bool
    needs_setup: bool
