"""Shared pytest fixtures for TrialLens Lite backend tests.

Most of the suite (health endpoints, normalize/dedup logic, chunking,
fusion, the ClinicalTrials.gov/PubMed/embedding clients) never touches a
live Postgres instance. The `db_session` fixture below is the one
exception, used by the ingestion and retrieval DB-integration tests —
it's skipped automatically if no database is reachable *or* if the
`vector` extension isn't installed (chunks.embedding needs it), so the
rest of the suite still runs without either.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.deps import get_claude_client_dependency, get_embedding_provider_dependency
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Importing app.models registers every table on Base.metadata.
import app.models  # noqa: F401,E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    """Make sure no test leaks its dependency override into the next one.

    ``get_claude_client_dependency``/``get_embedding_provider_dependency``
    (app/api/deps.py, added in Phase 6) are included alongside ``get_db``
    for the same reason: tests/test_end_to_end.py overrides the Claude
    client with a scripted fake, and this fixture is what keeps that
    override from leaking into an unrelated test.
    """

    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_claude_client_dependency, None)
    app.dependency_overrides.pop(get_embedding_provider_dependency, None)


@pytest.fixture(scope="session")
def _db_engine():
    """A Postgres engine with all tables created, or a skip if none of the
    configured DATABASE_URL is reachable in this environment.
    """

    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres not reachable at {settings.database_url}: {exc}")

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001
        # Most commonly: the `vector` extension isn't installed on this
        # Postgres server, so the chunks.embedding column can't be
        # created. That's an environment gap, not a code bug — skip
        # rather than fail.
        pytest.skip(f"Could not create schema (often a missing `vector` extension): {exc}")

    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(_db_engine):
    """A Session bound to a transaction that's rolled back after the
    test, so ingestion tests never leave rows behind for one another.
    """

    connection = _db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
