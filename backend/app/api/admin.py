"""One-time deployment-administration endpoints.

``POST /admin/migrate`` runs ``alembic upgrade head`` against the
configured database. It exists purely so a freshly provisioned managed
Postgres (Neon, Vercel Postgres, etc.) can be brought up to the current
schema from a deployed environment that has network access to it, without
ever needing the raw connection string outside that environment - the
serverless function already has ``DATABASE_URL`` injected, and this just
reuses it via ``app.core.config.Settings``.

Gated by ``settings.admin_token``: with no token configured (the default)
every request is rejected. An operator sets ``ADMIN_TOKEN`` on the
deployment, calls this once, then unsets it again - this is not meant to
stay reachable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_settings_dependency
from app.core.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# app/api/admin.py -> app/api -> app -> backend (alembic/ lives here)
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _require_admin_token(token: str | None, settings: Settings) -> None:
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
        )


@router.post("/admin/migrate")
def migrate(
    token: str | None = None,
    settings: Settings = Depends(get_settings_dependency),
) -> dict[str, str]:
    """Run `alembic upgrade head`. Requires `?token=<ADMIN_TOKEN>`."""

    _require_admin_token(token, settings)

    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    cfg.set_main_option("version_path_separator", "os")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)

    try:
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        logger.exception("alembic upgrade head failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"migration failed: {exc}",
        ) from exc

    return {"status": "migrated"}
