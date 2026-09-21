# Phase 2 notes

What Phase 2 built: SQLAlchemy models for `Trial`, `Publication`,
`Document`, `Chunk`, `Citation`; an Alembic migration creating those
tables; ClinicalTrials.gov and PubMed ingestion scripts (query-based,
not a hardcoded ID list); pure normalization and duplicate-detection
modules; and a test suite (mocked HTTP fixtures for the API clients,
plus DB integration tests for the upsert/dedup logic).

Scope notes, since a couple of judgment calls aren't explicit in the
Phase 2 ask:

- `Chunk` and `Citation` are schema only — no rows are written yet.
  Splitting `Document.text` into chunks is bundled with embeddings in
  the next phase; citations aren't populated until Q&A exists. Creating
  the tables now (empty) matches "SQLAlchemy models for ... chunks, and
  citations" without jumping ahead to chunking logic or embeddings.
- The "small curated dataset" is a **search query** (drug name
  "pembrolizumab", `page_size=10`), not a hardcoded list of specific
  NCT IDs/PMIDs — hand-picking specific identifiers from memory risked
  baking in wrong or stale IDs into the codebase. Whoever runs the
  ingestion scripts fetches whatever the live APIs currently return for
  that query. See `app/ingestion/config.py`.

## What was actually verified, and how

Same sandbox as Phase 1: no outbound access to PyPI, so `sqlalchemy`,
`alembic`, `httpx`, and `pytest` are still not importable here, and
`clinicaltrials.gov` / `eutils.ncbi.nlm.nih.gov` are also blocked (403)
— confirmed directly, not assumed. Given that:

Verified for real:

- `python3.12 -m py_compile` over every backend and test file — all
  syntactically valid.
- The **migration's DDL**, translated 1:1 into raw SQL and applied with
  `psql` against a real local Postgres 16: all five tables created
  cleanly. (Phase 2 introduces no `vector` columns, so — unlike Phase
  1's pgvector extension — this schema needed nothing beyond stock
  Postgres to verify.)
- Every constraint in that schema, exercised with real INSERT/DELETE
  statements against that database: duplicate `nct_id` rejected (unique
  index), a document with both/neither `trial_id` and `publication_id`
  rejected (XOR check), a second document for the same trial rejected
  (partial unique index), an invalid `source_type` rejected (CHECK), an
  inverted chunk char range rejected (CHECK), and deleting a trial
  correctly cascade-deletes its document.
- `app/ingestion/normalize.py` and `app/ingestion/dedup.py` have zero
  third-party imports (stdlib only), so they run natively in this
  sandbox. All 40 assertions mirrored from the pytest suite — trial/
  publication field extraction, partial-date parsing, content-hash
  determinism and change-detection, NCT-ID extraction/dedup, and the
  three dedup classifications — were executed directly and passed.

Not verified in this environment (blocked by network access, not a
known defect):

- `alembic upgrade head` itself (alembic isn't installed here).
- The API client tests (`test_clinicaltrials_client.py`,
  `test_pubmed_client.py`) — these need `httpx`.
- The DB integration tests (`test_ingest_upsert.py`) — these need
  `sqlalchemy`.
- An actual end-to-end ingestion run against the live APIs.

## Commands to finish verification yourself

```bash
cd backend && source .venv/bin/activate  # from Phase 1 setup
alembic upgrade head

cd .. && pytest   # full suite, including the mocked-fixture and DB tests

# then a real ingestion run:
cd backend
python -m app.ingestion.ingest_clinicaltrials --limit 5 --verbose
python -m app.ingestion.ingest_pubmed --limit 5 --verbose
```

If `alembic upgrade head` fails, that's worth comparing line-by-line
against `docs phase-2-notes.md`'s raw-SQL version above — the two
should be equivalent; a difference between them is a real migration bug.
