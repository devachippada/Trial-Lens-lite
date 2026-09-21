"""Retrieval orchestration: full-text, dense, or RRF-fused hybrid search.

This is what the API endpoint (app/api/retrieval.py) calls. Kept
independent of FastAPI/Pydantic so it's testable on its own — it takes
a plain SQLAlchemy ``Session`` and an ``EmbeddingProvider`` and returns
plain dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.retrieval.config import DEFAULTS
from app.retrieval.dense import dense_search
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.fulltext import fulltext_search
from app.retrieval.fusion import reciprocal_rank_fusion

RetrievalMode = Literal["hybrid", "fulltext", "dense"]


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: int
    document_id: int
    source_type: str
    source_identifier: str
    source_url: str
    title: str
    excerpt: str
    score: float
    matched_by: list[str]


def _load_results(
    session: Session, fused, matched_by: dict[int, list[str]]
) -> list[RetrievalResult]:
    """Join fused (chunk_id, score) results back to Chunk+Document rows."""

    chunk_ids = [item.item_id for item in fused]
    if not chunk_ids:
        return []

    rows = (
        session.query(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.id.in_(chunk_ids))
        .all()
    )
    by_chunk_id = {chunk.id: (chunk, document) for chunk, document in rows}

    results = []
    for item in fused:
        pair = by_chunk_id.get(item.item_id)
        if pair is None:
            continue  # stale/deleted chunk between search and fetch; skip rather than error
        chunk, document = pair
        results.append(
            RetrievalResult(
                chunk_id=chunk.id,
                document_id=document.id,
                source_type=document.source_type,
                source_identifier=document.source_identifier,
                source_url=document.source_url,
                title=document.title,
                excerpt=chunk.text,
                score=item.score,
                matched_by=matched_by.get(item.item_id, []),
            )
        )
    return results


def search(
    session: Session,
    query: str,
    embedding_provider: EmbeddingProvider,
    mode: RetrievalMode = "hybrid",
    top_k: int = DEFAULTS.default_top_k,
    candidate_pool_size: int = DEFAULTS.candidate_pool_size,
    rrf_k: int = DEFAULTS.rrf_k,
) -> list[RetrievalResult]:
    """Run full-text, dense, or RRF-fused hybrid retrieval over chunks."""

    if not query or not query.strip():
        return []

    rankings: list[list[int]] = []
    labels: list[str] = []

    if mode in ("hybrid", "fulltext"):
        hits = fulltext_search(session, query, limit=candidate_pool_size)
        rankings.append([hit.chunk_id for hit in hits])
        labels.append("fulltext")

    if mode in ("hybrid", "dense"):
        [query_embedding] = embedding_provider.embed([query])
        hits = dense_search(session, query_embedding, limit=candidate_pool_size)
        rankings.append([hit.chunk_id for hit in hits])
        labels.append("dense")

    fused = reciprocal_rank_fusion(rankings, k=rrf_k)[:top_k]

    matched_by: dict[int, list[str]] = {
        item.item_id: [labels[i] for i in sorted(item.source_ranks)] for item in fused
    }

    return _load_results(session, fused, matched_by)
