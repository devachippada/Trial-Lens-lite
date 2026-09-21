"""Chunk schema for retrieval.

A contiguous slice of a ``Document``'s text, carrying both a dense
embedding (pgvector, Phase 3) and a generated full-text-search vector
(``text_tsv``, populated automatically by Postgres from ``text`` — the
app never writes to it) so the same row supports both retrieval paths.
"""

from __future__ import annotations

import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.retrieval.config import EMBEDDING_DIMENSION


class Chunk(Base):
    """A contiguous slice of a ``Document``'s text."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        CheckConstraint("char_end > char_start", name="ck_chunks_char_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Character offsets into the parent Document.text, so a citation can
    # point back at exactly the excerpt it used.
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Dense retrieval (Phase 3). Nullable because chunks can exist before
    # (re-)embedding runs, or if `raw_data`'s document was chunked but the
    # embedding step failed for that batch.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )

    # Full-text retrieval (Phase 3). Generated/stored by Postgres itself
    # from `text` — read-only from the app's point of view, so there's no
    # corresponding constructor argument or assignment anywhere.
    text_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=True,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
    citations: Mapped[list["Citation"]] = relationship(  # noqa: F821
        back_populates="chunk", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Chunk(document_id={self.document_id}, chunk_index={self.chunk_index})"
