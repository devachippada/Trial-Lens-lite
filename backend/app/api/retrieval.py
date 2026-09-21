"""Retrieval API: GET /api/v1/retrieve.

Returns ranked chunks with citation metadata (source type/identifier/
URL) and an excerpt — no generation happens here, this is retrieval
only. Claude-backed answering is a later phase.

The embedding provider is ``Depends()``-injected (see ``app/api/deps.py``)
rather than called directly inside the handler, for the same reason as
``app/api/qa.py`` — it gives ``app.dependency_overrides`` a real seam,
even though this particular endpoint's ``tests/test_end_to_end.py``
coverage doesn't need to override it (the hashing provider needs no
network/API key and can run as-is).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_embedding_provider_dependency
from app.db.session import get_db
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.hybrid import search as hybrid_search
from app.retrieval.config import DEFAULTS
from app.schemas.retrieval import RetrievalResponse, RetrievalResultOut

router = APIRouter(tags=["retrieval"])


@router.get("/retrieve", response_model=RetrievalResponse)
def retrieve(
    q: str = Query(..., min_length=1, description="Search query"),
    k: int = Query(DEFAULTS.default_top_k, ge=1, le=50, description="Number of results"),
    mode: Literal["hybrid", "fulltext", "dense"] = Query(
        "hybrid", description="Retrieval strategy"
    ),
    db: Session = Depends(get_db),
    provider: EmbeddingProvider = Depends(get_embedding_provider_dependency),
) -> RetrievalResponse:
    results = hybrid_search(db, query=q, embedding_provider=provider, mode=mode, top_k=k)

    return RetrievalResponse(
        query=q,
        mode=mode,
        results=[RetrievalResultOut(**vars(r)) for r in results],
    )
