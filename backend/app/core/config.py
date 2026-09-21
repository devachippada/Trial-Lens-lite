"""Application configuration.

All runtime configuration is read from environment variables (see
``.env.example`` at the repository root). We use ``pydantic-settings`` so
values are validated once at startup rather than sprinkled through the
codebase as ``os.environ`` lookups.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    Phase 1 only needs enough here to stand up the API and connect to
    Postgres. Retrieval / ingestion / LLM-specific settings are added in
    later phases so this file stays easy to review.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App -------------------------------------------------------------
    app_name: str = "TrialLens Lite API"
    app_env: str = "development"
    # Not currently wired to anything (app/main.py never passes it to
    # FastAPI's own `debug=`, and nothing else reads it) - flagged and
    # fixed to a safe default during the release-hardening audit: a
    # field named "debug" defaulting to True is a misleading, insecure-
    # looking default even though today it has no actual effect on
    # error verbosity. Left unused deliberately rather than wired up,
    # since doing that is a behavior change outside this audit's
    # fix-only-defects scope - see docs/release-report.md.
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- CORS --------------------------------------------------------------
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # --- Database ----------------------------------------------------------
    database_url: str = (
        "postgresql+psycopg://triallens:triallens@localhost:5432/triallens"
    )

    # --- Anthropic (used by app/generation/, Phase 4) -----------------------
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    # --- Ingestion sources (Phase 2) ----------------------------------------
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"
    pubmed_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    # Optional but recommended by NCBI E-utilities usage guidelines
    # (https://www.ncbi.nlm.nih.gov/books/NBK25497/) to identify the
    # caller and get a higher rate limit.
    ncbi_api_key: str | None = None
    ncbi_contact_email: str | None = None

    # --- Retrieval / embeddings (Phase 3) -----------------------------------
    # "hashing" (default, no network/API key) or "voyage" (real embeddings).
    # See app/retrieval/embeddings.py. embedding_dimension must match the
    # `chunks.embedding` column width from
    # alembic/versions/0003_add_retrieval_columns.py — it isn't safe to
    # change on a database that already has embedded chunks.
    embedding_provider: str = "hashing"
    embedding_dimension: int = 256
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-3-large"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    ``lru_cache`` means the environment is only parsed once per process,
    while still being easy to override in tests via
    ``get_settings.cache_clear()``.
    """

    return Settings()
