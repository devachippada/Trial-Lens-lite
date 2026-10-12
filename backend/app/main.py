"""FastAPI application entrypoint for TrialLens Lite.

App wiring, CORS, health/readiness, retrieval (Phase 3), and (as of
Phase 4) Claude-backed Q&A and trial comparison. Ingestion and
chunk-indexing still run as offline CLI scripts, not API endpoints (see
app/ingestion/ and app/retrieval/index_documents.py).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.qa import router as qa_router
from app.api.retrieval import router as retrieval_router
from app.core.config import get_settings

settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Clinical-trial literature assistant: searches ClinicalTrials.gov "
            "and PubMed, retrieves evidence, and answers questions using only "
            "retrieved context with validated citations."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health/readiness live at the root, not under /api/v1, so container
    # orchestrators and load balancers can probe them without knowing about
    # API versioning.
    app.include_router(health_router)
    app.include_router(retrieval_router, prefix=settings.api_v1_prefix)
    app.include_router(qa_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
