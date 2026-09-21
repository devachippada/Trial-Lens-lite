"""Pydantic response models for the retrieval API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalResultOut(BaseModel):
    chunk_id: int
    document_id: int
    source_type: str
    source_identifier: str
    source_url: str
    title: str
    excerpt: str
    score: float
    matched_by: list[str] = Field(
        description="Which retrievers ('fulltext', 'dense') surfaced this chunk."
    )


class RetrievalResponse(BaseModel):
    query: str
    mode: str
    results: list[RetrievalResultOut]
