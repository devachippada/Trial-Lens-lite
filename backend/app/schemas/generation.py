"""Pydantic request/response models for the Q&A and comparison endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CitationOut(BaseModel):
    index: int
    chunk_id: int
    document_id: int
    source_type: str
    source_identifier: str
    source_url: str
    title: str
    excerpt: str


class AnswerOut(BaseModel):
    status: Literal["answered", "insufficient_evidence", "validation_failed"]
    query: str
    answer: str | None
    citations: list[CitationOut]
    warnings: list[str]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int | None = Field(None, ge=1, le=30)


class CompareRequest(BaseModel):
    nct_id_a: str = Field(..., min_length=1)
    nct_id_b: str = Field(..., min_length=1)
    question: str | None = None
