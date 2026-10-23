from __future__ import annotations

import uuid

from docmind.ai.sources import Source


def source(
    text: str,
    *,
    n: int = 1,
    title: str = "Handbook",
    location: str = "Page 1",
    heading: str = "",
    document_id: uuid.UUID | None = None,
    tokens: int | None = None,
) -> Source:
    return Source(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid5(uuid.NAMESPACE_URL, title),
        document_title=title,
        location=location,
        heading=heading,
        text=text,
        token_count=tokens if tokens is not None else max(1, len(text) // 4),
        n=n,
    )
