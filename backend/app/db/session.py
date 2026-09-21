"""Database engine and session management.

Provides a single SQLAlchemy ``Engine`` for the process plus a
``get_db`` FastAPI dependency that yields a ``Session`` and guarantees it
is closed after the request, even on error.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_engine() -> Engine:
    """Expose the module-level engine (used by /ready and Alembic)."""

    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
