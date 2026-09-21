"""Sanity tests for app wiring/config that aren't specific to one route."""

from app.core.config import get_settings
from app.main import app


def test_settings_load_with_defaults():
    settings = get_settings()

    assert settings.app_name == "TrialLens Lite API"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_app_exposes_health_and_ready_routes():
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/ready" in paths
