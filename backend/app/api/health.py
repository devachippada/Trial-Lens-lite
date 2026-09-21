"""Liveness and readiness endpoints.

``/health`` answers "is the process up" and never touches external
dependencies, so it is safe for a container orchestrator's liveness probe.

``/ready`` answers "can this instance actually serve traffic" by running a
trivial query against Postgres. It is meant for readiness probes / smoke
tests, not for high-frequency polling.
"""

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Basic liveness check. Always returns 200 if the process is running."""

    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness check: verifies the database is reachable.

    Returns HTTP 200 with ``{"status": "ready"}`` when the DB responds, or
    HTTP 503 with ``{"status": "not_ready", "detail": ...}`` otherwise.
    """

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - we deliberately report any failure
        logger.warning("Readiness check failed: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "detail": "database unavailable"}

    return {"status": "ready"}
