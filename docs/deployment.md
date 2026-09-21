# Deployment

TrialLens Lite ships as three Docker Compose services: `db` (Postgres 16
with the `pgvector/pgvector:pg16` image, which bundles the `vector`
extension — this is the one piece of infrastructure the sandbox that
built this project could not fully exercise itself, since its bare-metal
Postgres install is missing that extension; see
`docs/known-limitations.md`), `backend` (FastAPI + Uvicorn), and
`frontend` (Next.js).

## Local development

```bash
cp .env.example .env
# Edit .env: at minimum set ANTHROPIC_API_KEY before using /ask or /compare.
# The rest of .env.example's defaults work as-is for local development.

make up
# equivalent to: docker compose up --build
```

This builds and starts all three services. The backend container's
startup command runs `alembic upgrade head` before starting Uvicorn, so
the schema (including the pgvector `embedding` column) is always current
on boot — see `backend/alembic/versions/` for the three migrations
(pgvector extension, ingestion domain tables, retrieval columns).

Once it's up:

- Frontend: http://localhost:3000
- Backend docs (FastAPI's automatic OpenAPI UI): http://localhost:8000/docs
- Health checks: `GET /health` (liveness) and `GET /ready` (readiness —
  actually pings the database)

## Loading data

The stack starts with an empty database. Ingestion and indexing are
offline CLI scripts, not API endpoints — run them inside the backend
container once it's up:

```bash
# Ingest a curated set of trials and publications (needs network access
# to clinicaltrials.gov / eutils.ncbi.nlm.nih.gov from wherever this runs):
docker compose exec backend python -m app.ingestion.ingest_clinicaltrials \
    --intervention pembrolizumab --status COMPLETED --limit 25
docker compose exec backend python -m app.ingestion.ingest_pubmed \
    --term "pembrolizumab AND clinical trial[pt]" --limit 25

# Chunk and embed everything just ingested:
docker compose exec backend python -m app.retrieval.index_documents --verbose
```

Both ingestion commands are safe to re-run — they upsert by source ID
and content hash (`app/ingestion/dedup.py`), so a second run only
changes what actually changed upstream.

To instead load the Phase 6 synthetic fixture corpus (useful for a demo
that doesn't depend on live network access to ClinicalTrials.gov/PubMed,
or for re-running the evaluation) and compute the evaluation report for
real:

```bash
docker compose exec backend python -m app.evaluation.run_eval --claude-client real
```

See `docs/evaluation-report.md` for what this actually measures and
`--claude-client fake-self-test` for running it without an API key (as a
plumbing self-test only — its citation/abstention numbers are not real
model performance in that mode).

## Configuration reference

Every setting lives in `.env` (see `.env.example` for the full list with
comments) and is read once at startup via `pydantic-settings`
(`backend/app/core/config.py`). The ones a real deployment should
actually change from their defaults:

| Variable | Default | Change for production because |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Required for `/ask` and `/compare` — without it, `get_claude_client` raises immediately rather than silently falling back to a fake answer generator (see `app/generation/client.py`). |
| `EMBEDDING_PROVIDER` | `hashing` | `hashing` needs no API key but is not semantically meaningful (see `docs/known-limitations.md`); set to `voyage` (plus `VOYAGE_API_KEY`) for real dense retrieval. |
| `POSTGRES_PASSWORD` | `triallens` | Change from the example default. |
| `CORS_ALLOW_ORIGINS` | `["http://localhost:3000"]` | Set to the real frontend origin(s). |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Set to the backend's real public URL — this is baked into the browser bundle, not read server-side at request time. |

`EMBEDDING_DIMENSION` (default 256) is schema-coupled to the
`chunks.embedding` pgvector column width set by migration `0003` — it
cannot be changed on a database that already has embedded chunks without
a new migration and a full re-index.

## Running the test suite against a real environment

This project's test suite needs packages this sandbox never had network
access to install (`sqlalchemy`, `alembic`, `fastapi`, `pytest`,
`pgvector`, `anthropic` — see `docs/known-limitations.md`'s environment
section for exactly which ones and why). In any environment with normal
package-registry access:

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Start a real Postgres with pgvector, e.g. via docker compose:
docker compose up -d db

cd ..
PYTHONPATH=backend pytest
```

`tests/conftest.py`'s `db_session`/`_db_engine` fixtures skip themselves
automatically (rather than failing) if Postgres isn't reachable or the
`vector` extension isn't installed, so `pytest` is always safe to run —
DB-integration tests, including Phase 6's `tests/test_end_to_end.py`,
just won't execute without a real database available.

## Frontend production build

```bash
cd frontend
npm install
npm run build
npm run start
```

`docker-compose.yml`'s `frontend` service runs `npm run dev` for local
development (with the source tree bind-mounted for hot reload); a real
deployment should build a production image running `npm run build` +
`npm run start` instead — see `frontend/Dockerfile` as the starting
point for a multi-stage production build (the current `Dockerfile` is
sized for local development, not a minimal production image).

## Health and readiness

Both are already wired for a container orchestrator or load balancer to
probe (Phase 1):

- `GET /health` — liveness only, no dependencies checked.
- `GET /ready` — pings the database; use this for a readiness probe.

Docker Compose's own `healthcheck` blocks in `docker-compose.yml` already
use these (`db`'s via `pg_isready`, `backend`'s via `curl -f
http://localhost:8000/health`), and `backend` won't start until `db`
reports healthy (`depends_on: condition: service_healthy`).
