# Phase 1 notes

What Phase 1 built: FastAPI backend skeleton (`/health`, `/ready`),
SQLAlchemy + Alembic wiring with a first migration that enables the
Postgres `vector` extension, a Next.js + TypeScript + Tailwind homepage
that pings the backend, `docker-compose.yml` for db/backend/frontend, a
pytest suite for the health endpoints, and this repo's scaffolding.

## What was actually verified, and how

The environment this was built in had no outbound access to PyPI, the
npm registry, Docker Hub, or even the Ubuntu package archive for new
`.deb` downloads (all returned `403 Forbidden`) — only Anthropic's own
API endpoints were reachable. That ruled out installing FastAPI,
Next.js/React, pulling `pgvector/pgvector:pg16`, or adding the
`postgresql-16-pgvector` apt package in that sandbox. Given that, here
is exactly what was and wasn't confirmed there:

Verified for real:

- `docker compose config` — parses and validates `docker-compose.yml`
  (service definitions, env interpolation, volumes) without pulling any
  images. Passed cleanly.
- `python3.12 -m py_compile` over every backend `.py` file (app code,
  Alembic env/migration, tests) — confirms they're syntactically valid
  Python 3.12. Passed cleanly.
- A real local PostgreSQL 16 server was started and a role/database were
  created against it successfully. The `vector` extension itself could
  not be added (its package couldn't be downloaded), so the pgvector
  part of that check is unverified in this environment.

Not verified in this environment (blocked by network access, not a
known defect):

- `pip install -r backend/requirements-dev.txt` (FastAPI, SQLAlchemy,
  Alembic, uvicorn, psycopg, pgvector-python, anthropic, pytest, ruff).
- `npm install` for the frontend (Next.js, React, Tailwind, TypeScript).
- `docker compose up --build` end-to-end (needs the above, plus pulling
  the `pgvector/pgvector:pg16` and `node:22-slim` images).
- `pytest` actually executing the test suite (needs the packages above
  installed; only syntax was checked, not imports/behavior).

## Commands to finish verification yourself

In a normal environment (a laptop, CI, or any sandbox with normal
internet access):

```bash
cp .env.example .env
docker compose up --build
# then: curl http://localhost:8000/health
#       curl http://localhost:8000/ready
#       open http://localhost:3000

# and, for the test suite:
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cd ..
pytest
```

If either fails, it's a real bug to fix — everything above this point in
Phase 1 has not yet been exercised against the real dependencies.
