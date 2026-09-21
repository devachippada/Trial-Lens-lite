"""Registered-trial records ingested from ClinicalTrials.gov.

One row per NCT number. ``raw_data`` keeps the full API response verbatim
so nothing is lost if our normalized columns miss a field — every
normalized value here should be traceable back to it.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Trial(Base):
    """A single registered trial (one row per ``nct_id``)."""

    __tablename__ = "trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Source identifier ---------------------------------------------
    nct_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Registry metadata (preserved as published) ---------------------
    brief_title: Mapped[str] = mapped_column(Text, nullable=False)
    official_title: Mapped[str | None] = mapped_column(Text)
    overall_status: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(32))
    study_type: Mapped[str | None] = mapped_column(String(64))

    conditions: Mapped[list[str] | None] = mapped_column(JSONB)
    intervention_names: Mapped[list[str] | None] = mapped_column(JSONB)
    sponsor_name: Mapped[str | None] = mapped_column(String(500))
    enrollment_count: Mapped[int | None] = mapped_column(Integer)

    start_date: Mapped[dt.date | None] = mapped_column(Date)
    primary_completion_date: Mapped[dt.date | None] = mapped_column(Date)
    completion_date: Mapped[dt.date | None] = mapped_column(Date)
    last_update_posted_date: Mapped[dt.date | None] = mapped_column(Date)

    brief_summary: Mapped[str | None] = mapped_column(Text)
    detailed_description: Mapped[str | None] = mapped_column(Text)

    # Preserve endpoints exactly as registered (list of {"measure","description","timeFrame"}).
    primary_outcomes: Mapped[list[dict] | None] = mapped_column(JSONB)
    secondary_outcomes: Mapped[list[dict] | None] = mapped_column(JSONB)

    # --- Ingestion bookkeeping -------------------------------------------
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="trial", cascade="all, delete-orphan"
    )
    publications: Mapped[list["Publication"]] = relationship(  # noqa: F821
        back_populates="linked_trial"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Trial(nct_id={self.nct_id!r}, status={self.overall_status!r})"
