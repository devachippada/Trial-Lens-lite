"""Declarative base for SQLAlchemy models.

Phase 1 has no domain models yet. Future phases will define ORM models
under ``app/models`` and import them here (or in ``alembic/env.py``) so
that Alembic's autogenerate can see them via ``Base.metadata``.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
