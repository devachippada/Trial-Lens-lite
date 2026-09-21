"""Unified text document ready for future chunking (Phase 3).

Exactly one of ``trial_id`` / ``publication_id`` is set — a ``Document``
is always sourced from a registered trial or a publication, never both.
Enforced with a DB-level CHECK constraint so it can't drift even if
application code has a bug.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

VALID_SOURCE_TYPES = ("trial", "publication")


class Document(Base):
    """One document per ingested trial/publication (1:1 in Phase 2)."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "(trial_id IS NOT NULL) <> (publication_id IS NOT NULL)",
            name="ck_documents_exactly_one_source",
        ),
        CheckConstraint(
            f"source_type IN {VALID_SOURCE_TYPES}",
            name="ck_documents_source_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    trial_id: Mapped[int | None] = mapped_column(ForeignKey("trials.id", ondelete="CASCADE"))
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE")
    )

    # Denormalized for convenient display/citation without a join.
    source_identifier: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    trial: Mapped["Trial | None"] = relationship(back_populates="documents")  # noqa: F821
    publication: Mapped["Publication | None"] = relationship(  # noqa: F821
        back_populates="documents"
    )
    chunks: Mapped[list["Chunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan", order_by="Chunk.chunk_index"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Document(source_type={self.source_type!r}, source_identifier={self.source_identifier!r})"
