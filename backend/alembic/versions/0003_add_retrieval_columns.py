"""add chunk embedding (pgvector) and full-text search columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

Phase 3: adds dense (pgvector) and sparse (Postgres full-text) retrieval
support directly on `chunks`. `embedding`'s width (EMBEDDING_DIMENSION)
is schema-coupled with app/retrieval/config.py and whichever
EmbeddingProvider is configured — see that module's docstring before
changing either independently.

Requires the `vector` extension (enabled by migration 0001) to actually
be installed on the Postgres server, not just declared — see
docs/phase-3-notes.md for how that was and wasn't verified.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.retrieval.config import EMBEDDING_DIMENSION

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Dense retrieval ---------------------------------------------------
    op.add_column("chunks", sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True))
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # --- Full-text retrieval -------------------------------------------------
    # GENERATED ALWAYS ... STORED has no first-class Alembic op, so this is
    # raw SQL; the ORM model (app/models/chunk.py) mirrors it with
    # sqlalchemy.Computed so Base.metadata.create_all() (used by tests)
    # produces the same column.
    op.execute(
        "ALTER TABLE chunks ADD COLUMN text_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_text_tsv ON chunks USING gin (text_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_text_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_tsv")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_column("chunks", "embedding")
