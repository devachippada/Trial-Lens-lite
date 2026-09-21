# Phase 3 notes

What Phase 3 built: pure text chunking (`app/retrieval/chunking.py`); a
configurable embedding provider (`app/retrieval/embeddings.py` —
dependency-free deterministic hashing provider by default, real Voyage
AI HTTP provider as an opt-in); a migration adding a pgvector
`embedding` column and a generated `text_tsv` full-text column to
`chunks`; full-text search (`fulltext.py`), dense/cosine search
(`dense.py`), and reciprocal-rank-fusion hybrid search (`fusion.py`,
`hybrid.py`); a chunk-indexing CLI (`index_documents.py`) that (re-)chunks
and embeds every `Document`; a `GET /api/v1/retrieve` endpoint; and a
retrieval test suite.

Scope notes:

- `EMBEDDING_PROVIDER=hashing` is the default so the whole pipeline
  (chunk → embed → store → search) works with zero external
  dependencies or API keys — useful for this sandbox and for anyone
  demoing the project without a Voyage account. It is a real technique
  (feature hashing), not a fabricated stand-in, but it captures none of
  a trained model's semantics — swap to `EMBEDDING_PROVIDER=voyage` for
  retrieval quality that means anything.
- `index_documents.py` is a separate offline CLI step, not something the
  API triggers, matching the "ingestion/indexing runs offline, the API
  only serves" pattern established in Phase 2.
- The retrieval endpoint returns ranked chunks with citation-shaped
  metadata (source type/identifier/URL, excerpt) but doesn't generate an
  answer — that's Claude-backed Q&A, explicitly out of scope for this
  phase.

## What was actually verified, and how

Same sandbox as Phases 1–2, re-confirmed rather than assumed: no
outbound access to PyPI (`pip install sqlalchemy` fails with "No
matching distribution found", not a timeout — a real block, not a flaky
network), so `sqlalchemy`, `alembic`, `fastapi`, `pytest`, and `pgvector`
are still not importable here.

One thing *is* different from what Phases 1–2 assumed, and it's worth
being precise about: this sandbox's general-purpose Python actually has
`httpx` and `pydantic`/`pydantic-settings` already installed (pulled in
as transitive dependencies of unrelated tooling, not installed for this
project). That made it possible to verify more of Phase 3 for real than
Phase 2 documented — see below.

Verified for real:

- `python3.12 -m py_compile` over every file in `backend/app/`,
  `backend/alembic/`, and `tests/` — all syntactically valid, including
  every new Phase 3 module and all four new test files.
- **`app/retrieval/chunking.py`** — zero third-party imports. Every
  assertion in `tests/test_chunking.py` was executed directly against
  the real module: empty/whitespace-only input, single-span short text,
  leading-whitespace handling, char_start/char_end always slicing back
  to the exact original text, span length never exceeding `chunk_size`,
  a hand-traced 19-character example confirming whitespace-snapped
  boundaries and exact `chunk_overlap` overlap between consecutive
  spans, and all three parameter-validation `ValueError`s.
  - One assertion in the first draft of this test was wrong, not the
    code: a text ending in a space can have that trailing space swept
    into the final chunk (the code only skips *leading* whitespace at
    the start of each window, never trims trailing whitespace off the
    very last one). Running the test against the real function caught
    this immediately; the test was corrected to use a stripped fixture
    string instead of asserting behavior the code never promised.
- **`app/retrieval/fusion.py`** — zero third-party imports. Every
  assertion in `tests/test_fusion.py` was executed directly: empty
  input, order preservation for a single ranking, exact RRF scores for
  a hand-computed two-list example, agreement-across-lists outranking a
  single-list top hit, `source_ranks` bookkeeping, descending sort, and
  the `k <= 0` validation error.
  - Same story here: the first draft of the duplicate-handling test
    assumed rank is "position among unique items," but the real code
    assigns rank by raw list position (duplicates included) before
    dedup — so a duplicate earlier in the list pushes a later item to a
    worse rank than the number of *unique* items before it would
    suggest. Running it against the real function surfaced the wrong
    assumption in the test (not a code change) and it was corrected.
- **`app/retrieval/embeddings.py`** — `HashingEmbeddingProvider` has
  zero third-party imports; every assertion in `tests/test_embeddings.py`
  covering it (dimension, determinism, case-insensitivity, distinct
  inputs embedding differently, L2 normalization, the empty-string zero
  vector, and batch/solo consistency) was executed directly and passed.
  Because `httpx` happens to already be present in this sandbox (see
  above), the `VoyageEmbeddingProvider` and `get_embedding_provider`
  factory tests — built on `httpx.MockTransport`, the same pattern as
  Phase 2's API-client tests, so still zero real network calls — were
  *also* executed directly and passed: correct request payload
  (`input`/`model`/`output_dimension`/`input_type`), response
  `index`-sorting when the mock returns items out of order, the
  empty-input short-circuit that makes no request at all, HTTP error
  propagation, and all four `get_embedding_provider` branches (hashing
  default, voyage missing key → `RuntimeError`, voyage wired correctly
  through a mock client, unknown provider → `ValueError`).
- **The full-text search mechanism** (`ts_rank`/`plainto_tsquery` against
  a `GENERATED ALWAYS ... STORED tsvector` column with a GIN index) —
  the exact SQL from `app/retrieval/fulltext.py::fulltext_search` was
  run against a real, disposable Postgres 16 database (`psql`, not
  simulated): the generated column and GIN index were created without
  error, a query for "overall survival" correctly ranked and returned
  only the two matching rows (identical scores, since both contain the
  same two terms once), and a query for unrelated terms correctly
  matched zero rows.
- **Confirmed, precisely, why pgvector can't be verified here**: it's
  not just "not installed," the extension's control file is absent from
  disk (`CREATE EXTENSION vector` fails with "Could not open extension
  control file
  /usr/share/postgresql/16/extension/vector.control: No such file or
  directory"). That's an installation gap on this Postgres server, not
  a permissions or network issue reachable from inside this sandbox —
  installing it needs either the blocked apt package
  (`postgresql-16-pgvector`) or a from-source build, and both need
  outbound network this sandbox doesn't have.

Not verified in this environment (blocked by network/missing packages,
not a known defect):

- `alembic upgrade head` for migration 0003 itself (`alembic` isn't
  installed here).
- Anything touching the real `chunks.embedding` pgvector column or the
  `dense_search`/hybrid ORM code path — `sqlalchemy` and `pgvector`
  (the Python package) aren't importable here, and the `vector`
  extension isn't installable on this Postgres server (see above). This
  covers `tests/test_retrieval_hybrid.py` in full (`TestDenseSearch` and
  `TestHybridSearch`; `TestFulltextSearch` in that same file needs
  `sqlalchemy` too, even though the underlying SQL was verified
  separately via raw `psql` above), and `app/api/retrieval.py` /
  `index_documents.py` end-to-end.
- Whether `GET /api/v1/retrieve` actually starts and serves a request
  (`fastapi`/`uvicorn` aren't importable here).

## Commands to finish verification yourself

```bash
cd backend && source .venv/bin/activate  # from Phase 1 setup
pip install -r requirements-dev.txt      # now includes pgvector

alembic upgrade head                     # applies migration 0003

cd .. && pytest                          # full suite, including:
                                          #   tests/test_chunking.py
                                          #   tests/test_fusion.py
                                          #   tests/test_embeddings.py
                                          #   tests/test_retrieval_hybrid.py

# Index a few already-ingested documents (Phase 2's ingestion scripts
# must have been run first so there's something to chunk):
cd backend
python -m app.retrieval.index_documents --verbose

# Then query it:
uvicorn app.main:app --reload &
curl "http://localhost:8000/api/v1/retrieve?q=overall+survival&mode=hybrid&k=5"
curl "http://localhost:8000/api/v1/retrieve?q=overall+survival&mode=fulltext"
curl "http://localhost:8000/api/v1/retrieve?q=overall+survival&mode=dense"
```

If `alembic upgrade head` fails on the `CREATE INDEX ... USING hnsw`
step, that almost always means the `vector` extension isn't installed
on *your* Postgres server either — `postgresql-16-pgvector` (Debian/
Ubuntu) or the `pgvector/pgvector:pg16` Docker image (already what
`docker-compose.yml` uses) both include it; a bare `postgres:16` image
or a from-scratch local install does not.

To try real embeddings instead of the default hashing provider, set in
`.env`:

```
EMBEDDING_PROVIDER=voyage
VOYAGE_API_KEY=your-key-here
```

then re-run `index_documents.py` — it re-embeds anything whose content
changed, and everything if you're switching providers (the old hashing
vectors and new Voyage vectors aren't comparable, so a full re-index is
the safe move rather than something this project does automatically for
you).
