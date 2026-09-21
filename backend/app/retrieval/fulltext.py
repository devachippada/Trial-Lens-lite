"""Postgres full-text search over `chunks.text_tsv`.

`text_tsv` is a generated column (see the Chunk model / migration
0003) kept in sync by Postgres itself — this module only ever reads it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.types import ScoredChunk


def fulltext_search(session: Session, query: str, limit: int) -> list[ScoredChunk]:
    """Rank chunks by Postgres ``ts_rank`` against ``plainto_tsquery``.

    ``plainto_tsquery`` treats the query as plain keywords (ANDed
    together after stemming/stopword removal), which is the friendliest
    default for a search box — no tsquery syntax (``&``, ``|``, ``!``)
    leaks to callers of this function.
    """

    sql = text(
        """
        SELECT id, ts_rank(text_tsv, plainto_tsquery('english', :query)) AS score
        FROM chunks
        WHERE text_tsv @@ plainto_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    rows = session.execute(sql, {"query": query, "limit": limit}).all()
    return [ScoredChunk(chunk_id=row.id, score=float(row.score)) for row in rows]
