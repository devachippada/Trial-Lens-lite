"""Claude-backed Q&A: POST /api/v1/ask and POST /api/v1/compare.

Both endpoints are thin wiring: they gather evidence (via
``app.retrieval.hybrid.search`` for ``/ask``, via a direct per-trial
chunk fetch for ``/compare`` — see
``app.generation.comparison.assemble_trial_chunks``) and hand it, plus a
``ClaudeClient``, to ``app.generation.answer``/``app.generation.comparison``,
which do the actual grounded-generation/validation work and are what's
covered by the generation test suite (``tests/test_answer_generation.py``,
``tests/test_comparison.py``, etc.) without needing a running server.

The embedding provider and Claude client are ``Depends()``-injected (see
``app/api/deps.py``) rather than called directly, specifically so
``tests/test_end_to_end.py`` can override the Claude client with a
scripted fake for the one real network call this project can't make in
this sandbox, without touching anything else in these handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_claude_client_dependency, get_embedding_provider_dependency
from app.db.session import get_db
from app.generation.answer import AnswerResult, generate_answer
from app.generation.citations import CitationRecord
from app.generation.client import ClaudeClient
from app.generation.comparison import assemble_trial_chunks, generate_comparison
from app.generation.config import DEFAULTS
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.hybrid import search as hybrid_search
from app.schemas.generation import AnswerOut, AskRequest, CitationOut, CompareRequest

router = APIRouter(tags=["generation"])


def _to_citation_out(citation: CitationRecord) -> CitationOut:
    # `finalize_response` only ever puts citations with a resolved chunk
    # into `AnswerResult.citations` (it filters on `citation.is_valid`
    # before returning "answered") — this assert documents and checks
    # that invariant rather than silently trusting it.
    chunk = citation.chunk
    assert chunk is not None, "AnswerResult.citations must only contain resolved citations"
    return CitationOut(
        index=citation.index,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        source_type=chunk.source_type,
        source_identifier=chunk.source_identifier,
        source_url=chunk.source_url,
        title=chunk.title,
        excerpt=chunk.excerpt,
    )


def _to_answer_out(result: AnswerResult) -> AnswerOut:
    return AnswerOut(
        status=result.status,
        query=result.query,
        answer=result.answer,
        citations=[_to_citation_out(citation) for citation in result.citations],
        warnings=result.warnings,
    )


@router.post("/ask", response_model=AnswerOut)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider_dependency),
    claude_client: ClaudeClient = Depends(get_claude_client_dependency),
) -> AnswerOut:
    top_k = payload.top_k or DEFAULTS.top_k_chunks

    result = generate_answer(
        query=payload.question,
        retrieve=lambda: hybrid_search(
            db, payload.question, embedding_provider, mode="hybrid", top_k=top_k
        ),
        claude_client=claude_client,
    )
    return _to_answer_out(result)


@router.post("/compare", response_model=AnswerOut)
def compare(
    payload: CompareRequest,
    db: Session = Depends(get_db),
    claude_client: ClaudeClient = Depends(get_claude_client_dependency),
) -> AnswerOut:
    chunks_a = assemble_trial_chunks(db, payload.nct_id_a, limit=DEFAULTS.max_chunks_per_trial)
    if chunks_a is None:
        raise HTTPException(status_code=404, detail=f"Trial {payload.nct_id_a!r} not found")

    chunks_b = assemble_trial_chunks(db, payload.nct_id_b, limit=DEFAULTS.max_chunks_per_trial)
    if chunks_b is None:
        raise HTTPException(status_code=404, detail=f"Trial {payload.nct_id_b!r} not found")

    if payload.question:
        result = generate_comparison(
            payload.nct_id_a, chunks_a, payload.nct_id_b, chunks_b, claude_client,
            question=payload.question,
        )
    else:
        result = generate_comparison(
            payload.nct_id_a, chunks_a, payload.nct_id_b, chunks_b, claude_client,
        )
    return _to_answer_out(result)
