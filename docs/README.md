# docs/

Design notes, architecture decisions, and evaluation write-ups for
TrialLens Lite, accumulated phase by phase. Each `phase-N-notes.md` is
that phase's own honest record of what was built, what was actually
verified (and how), and what wasn't — read the most recent one first if
you want the full picture of the project's current state.

- `phase-1-notes.md` — project scaffolding: folder layout, FastAPI/Next.js
  setup, Docker Compose, health/readiness endpoints.
- `phase-2-notes.md` — ingestion: SQLAlchemy models, ClinicalTrials.gov/
  PubMed clients, normalization, deduplication.
- `phase-3-notes.md` — retrieval: chunking, embeddings, full-text/dense/
  hybrid search, the `/api/v1/retrieve` endpoint.
- `phase-4-notes.md` — generation: Claude-backed Q&A and trial
  comparison, citation extraction/validation, prompt-injection defenses.
- `phase-5-notes.md` — frontend: trial/publication search, evidence
  chat, comparison view.
- `phase-6-notes.md` — evaluation, deployment docs, and this project's
  final architecture/limitations documentation. **Start here** for the
  most complete picture of what actually works and what doesn't.
- `evaluation-report.md` — the 20-question evaluation set's actual
  results: what ran for real in this sandbox, what didn't, and why.
- `architecture.md` — a Mermaid diagram of the full system plus the
  request-level data flow for `/ask`.
- `known-limitations.md` — clinical-safety commitments (with tests),
  scope exclusions, retrieval/evaluation limitations, and the
  environment gaps encountered while building this project.
- `deployment.md` — Docker Compose deployment, configuration reference,
  and how to load data and run the evaluation for real.
- `release-report.md` — the release-hardening audit performed after
  Phase 6: what was verified, what was fixed, actual test/evaluation
  results, and remaining risks (Critical/High/Medium/Low). **Read this
  before deciding whether to deploy anything here** — it explains why
  the project is not yet certified production-ready.
