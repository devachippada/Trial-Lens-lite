"""Citation schema (table only) for the future Q&A phase.

Phase 2 only defines this table — nothing populates it yet, since
answering questions with Claude is out of scope until a later phase.
When that phase lands, each citation attached to an answer will point
at the exact chunk and excerpt it came from, plus a denormalized copy
of the source identifier/URL/type so citations can be rendered and
validated without extra joins.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import VALID_SOURCE_TYPES


class Citation(Base):
    """A single validated citation: an exact excerpt from one chunk."""

    __tablename__ = "citations"
    __table_args__ = (
        CheckConstraint(
            f"source_type IN {VALID_SOURCE_TYPES}",
            name="ck_citations_source_type",
        ),
        CheckConstraint(
            "excerpt_char_end IS NULL OR excerpt_char_start IS NULL "
            "OR excerpt_char_end > excerpt_char_start",
            name="ck_citations_excerpt_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )

    excerpt_text: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_char_start: Mapped[int | None] = mapped_column(Integer)
    excerpt_char_end: Mapped[int | None] = mapped_column(Integer)

    # Denormalized for display/validation without joining back through
    # chunk -> document -> trial/publication.
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunk: Mapped["Chunk"] = relationship(back_populates="citations")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Citation(source_identifier={self.source_identifier!r})"
