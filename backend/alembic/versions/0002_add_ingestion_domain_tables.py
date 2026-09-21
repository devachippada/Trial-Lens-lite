"""add trials, publications, documents, chunks, citations

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11

Phase 2 baseline domain schema. Populates only trials/publications/
documents via ingestion; chunks and citations are created empty here —
chunking+embeddings and Q&A are later phases.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_TYPES = ("trial", "publication")


def upgrade() -> None:
    op.create_table(
        "trials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nct_id", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("brief_title", sa.Text(), nullable=False),
        sa.Column("official_title", sa.Text(), nullable=True),
        sa.Column("overall_status", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("study_type", sa.String(length=64), nullable=True),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("intervention_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sponsor_name", sa.String(length=500), nullable=True),
        sa.Column("enrollment_count", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("primary_completion_date", sa.Date(), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("last_update_posted_date", sa.Date(), nullable=True),
        sa.Column("brief_summary", sa.Text(), nullable=True),
        sa.Column("detailed_description", sa.Text(), nullable=True),
        sa.Column("primary_outcomes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("secondary_outcomes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_trials_nct_id", "trials", ["nct_id"], unique=True)
    op.create_index("ix_trials_content_hash", "trials", ["content_hash"])

    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pmid", sa.String(length=20), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("journal", sa.String(length=500), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("mesh_terms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("linked_nct_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "linked_trial_id",
            sa.Integer(),
            sa.ForeignKey("trials.id"),
            nullable=True,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_xml", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_publications_pmid", "publications", ["pmid"], unique=True)
    op.create_index("ix_publications_doi", "publications", ["doi"], unique=True)
    op.create_index("ix_publications_content_hash", "publications", ["content_hash"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column(
            "trial_id", sa.Integer(), sa.ForeignKey("trials.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source_identifier", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(trial_id IS NOT NULL) <> (publication_id IS NOT NULL)",
            name="ck_documents_exactly_one_source",
        ),
        sa.CheckConstraint(
            f"source_type IN {SOURCE_TYPES}",
            name="ck_documents_source_type",
        ),
    )
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index(
        "uq_documents_trial_id",
        "documents",
        ["trial_id"],
        unique=True,
        postgresql_where=sa.text("trial_id IS NOT NULL"),
    )
    op.create_index(
        "uq_documents_publication_id",
        "documents",
        ["publication_id"],
        unique=True,
        postgresql_where=sa.text("publication_id IS NOT NULL"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        sa.CheckConstraint("char_end > char_start", name="ck_chunks_char_range"),
    )
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])

    op.create_table(
        "citations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chunk_id", sa.Integer(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("excerpt_text", sa.Text(), nullable=False),
        sa.Column("excerpt_char_start", sa.Integer(), nullable=True),
        sa.Column("excerpt_char_end", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_identifier", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"source_type IN {SOURCE_TYPES}",
            name="ck_citations_source_type",
        ),
        sa.CheckConstraint(
            "excerpt_char_end IS NULL OR excerpt_char_start IS NULL "
            "OR excerpt_char_end > excerpt_char_start",
            name="ck_citations_excerpt_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("citations")
    op.drop_table("chunks")
    op.drop_index("uq_documents_publication_id", table_name="documents")
    op.drop_index("uq_documents_trial_id", table_name="documents")
    op.drop_table("documents")
    op.drop_table("publications")
    op.drop_table("trials")
