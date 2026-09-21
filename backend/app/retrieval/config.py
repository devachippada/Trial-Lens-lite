"""Defaults for chunking, embeddings, and hybrid retrieval.

Mirrors app/ingestion/config.py's pattern: plain constants here, provider
selection and secrets (which need env vars) live in app.core.config.

EMBEDDING_DIMENSION is schema-coupled: it must match the width of the
`chunks.embedding` pgvector column set by
alembic/versions/0003_add_retrieval_columns.py. Changing it after data
exists means a new migration to widen/narrow the column and
re-embedding everything — it isn't something a config change alone can
do safely, which is why it's a constant here rather than a live Setting.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalDefaults:
    chunk_size: int = 1000
    chunk_overlap: int = 150
    embedding_dimension: int = 256
    default_top_k: int = 10
    # Candidate pool each sub-retriever contributes before fusion — wider
    # than top_k so RRF has enough overlap to work with.
    candidate_pool_size: int = 40
    rrf_k: int = 60


DEFAULTS = RetrievalDefaults()
EMBEDDING_DIMENSION = DEFAULTS.embedding_dimension
