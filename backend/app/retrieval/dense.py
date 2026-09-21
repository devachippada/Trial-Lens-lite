"""pgvector cosine-similarity search over `chunks.embedding`.

Raw SQL (rather than the ORM) so the pgvector literal formatting and the
``<=>`` operator are in one obvious place. Requires the ``vector``
extension and the ``embedding`` column from migration 0003.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.types import ScoredChunk


def _to_pgvector_literal(vector: list[float]) -> str:
    """Format a Python list as a pgvector input literal, e.g. ``[0.1,0.2]``."""

    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


def dense_search(session: Session, query_embedding: list[float], limit: int) -> list[ScoredChunk]:
    """Rank chunks by cosine similarity to ``query_embedding``.

    Uses pgvector's ``<=>`` cosine *distance* operator (0 = identical
    direction, 2 = opposite) and reports ``1 - distance`` as the score,
    so higher-is-better matches ``ts_rank``'s convention. Chunks with no
    embedding yet are excluded rather than erroring.
    """

    literal = _to_pgvector_literal(query_embedding)
    sql = text(
        """
        SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
        FROM chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    )
    rows = session.execute(sql, {"embedding": literal, "limit": limit}).all()
    return [ScoredChunk(chunk_id=row.id, score=float(row.score)) for row in rows]
