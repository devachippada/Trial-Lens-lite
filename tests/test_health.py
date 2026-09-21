"""Tests for the Phase 1 /health and /ready endpoints."""

from app.db.session import get_db
from app.main import app


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_db_reachable(client):
    class _FakeSession:
        def execute(self, *_args, **_kwargs):
            return None

    def _fake_get_db():
        yield _FakeSession()

    app.dependency_overrides[get_db] = _fake_get_db

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_unreachable(client):
    class _BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("connection refused")

    def _broken_get_db():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = _broken_get_db

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
