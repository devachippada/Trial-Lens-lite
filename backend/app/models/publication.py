"""Published-results records ingested from PubMed.

One row per PMID. ``raw_xml`` keeps the exact ``PubmedArticle`` XML
returned by EFetch so every normalized field is auditable against the
source.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Publication(Base):
    """A single published article (one row per ``pmid``)."""

    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Source identifiers ----------------------------------------------
    pmid: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    doi: Mapped[str | None] = mapped_column(String(255), unique=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Publication metadata (preserved as published) -------------------
    title: Mapped[str] = mapped_column(Text, nullable=False)
    journal: Mapped[str | None] = mapped_column(String(500))
    publication_date: Mapped[dt.date | None] = mapped_column(Date)
    # PubMed dates are frequently partial (year-only, or year+month). When a
    # full date can't be parsed we still keep the year so nothing is lost.
    publication_year: Mapped[int | None] = mapped_column(Integer)

    authors: Mapped[list[str] | None] = mapped_column(JSONB)
    abstract: Mapped[str | None] = mapped_column(Text)
    mesh_terms: Mapped[list[str] | None] = mapped_column(JSONB)

    # NCT numbers found in DataBank/SecondarySourceId (or, as a fallback,
    # pattern-matched in the title/abstract). All raw matches are kept here
    # even if we don't have that trial locally; linked_trial_id is only set
    # when exactly one of them resolves to a row in `trials`.
    linked_nct_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    linked_trial_id: Mapped[int | None] = mapped_column(ForeignKey("trials.id"))

    # --- Ingestion bookkeeping ---------------------------------------------
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_xml: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    linked_trial: Mapped["Trial | None"] = relationship(  # noqa: F821
        back_populates="publications"
    )
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="publication", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Publication(pmid={self.pmid!r}, title={self.title[:40]!r})"
