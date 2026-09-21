# Release-Hardening Audit Report

This report covers a release-hardening audit of TrialLens Lite,
performed after Phase 6 (evaluation, deployment docs, README,
architecture/limitations documentation) was complete. The audit's
mandate was explicit: inspect the 18 items below, fix only genuine
defects, missing documentation, broken tests, insecure defaults, and
deployment blockers (no new features, no redesigns), and report actual
results honestly — **do not call this project production-ready if any
Critical or High-severity issue remains.**

**Verdict up front, per that instruction: this project is NOT
certified production-ready by this audit.** Two High-severity gaps
remain (below): the full stack has never actually been booted
end-to-end in any environment (no live backend process, no live
frontend build, no live Docker Compose stack, no migration ever applied
against a real pgvector-enabled database), and no real Claude API call
has ever been made against this code, so the project's core
grounded-generation and citation-safety claims are verified only at the
unit/structural level, never against real model behavior. Both are
disclosed in detail below, with exact commands for someone with normal
package/network/API-key access to close them.

Everything else — 190 of the project's 222 real test-suite invocations
executed directly with 0 failures, full static type-checking and
linting clean, two independently-reconstructed real-Postgres retrieval
runs, a clean secrets scan, complete environment-variable
documentation, and a line-by-line accuracy pass over the README and
supporting docs — is real, reproducible, and detailed below.

## Environment this audit ran in

Same sandbox class as every prior phase, re-confirmed at the start of
this audit and again after a mid-audit environment reset: no network
access to PyPI, the npm registry, or Docker Hub (all return `403
Forbidden` from the sandbox's egress proxy); no `sqlalchemy`,
`fastapi`, `pytest`, `anthropic`, or `psycopg`/`psycopg2` installed;
`httpx` **is** installed. New relative to the Phase 6 build segment: a
real `docker` CLI and daemon (previously absent entirely), and
standalone `ruff`/`mypy`/`black`/`eslint` binaries. These new tools
made real static analysis (checks 1, 12) and a precise diagnosis of the
Docker gap (check 3) possible for the first time in this project's
life — see below.

## Checks 1–18: findings

### 1. Backend starts cleanly

**Not run live** (needs `fastapi`/`sqlalchemy`/`uvicorn`, none
installed here) — same gap as every prior phase. What *was* done for
real: `python3 -m py_compile` over every `.py` file under `backend/app/`
and `tests/` (zero errors); a full `mypy --ignore-missing-imports` pass
over the same files (zero errors, see check 12); and direct execution
of 190 real test-suite invocations that import and exercise most of
`app/generation/`, `app/retrieval/embeddings.py`,
`app/retrieval/fusion.py`, `app/retrieval/chunking.py`,
`app/ingestion/normalize.py`/`dedup.py`, and the ingestion HTTP clients
(0 failures). `app/main.py` was reviewed by hand: `create_app()` wires
CORS, health/readiness, retrieval, and Q&A routers with no obvious
wiring defect. **Never actually booted as a live ASGI process against a
real database in this sandbox, in this project's entire history.**

### 2. Frontend builds cleanly

**Not run live** (`npm install` fails immediately with `403 Forbidden`
against `registry.npmjs.org` — confirmed again this segment, unchanged
since Phase 5 — so `node_modules` cannot be populated and `next build`
cannot run). What *was* done for real: every one of the 26 real
`.ts`/`.tsx` files in the frontend (24 under `src/`, plus
`tailwind.config.ts` and `vitest.config.ts`; `next-env.d.ts` is
unmodified Next.js boilerplate, verified by inspection) was parsed with
the real TypeScript compiler (`ts.transpileModule`, global `typescript`
6.0.3) — **0 syntax errors**, matching Phase 5's count and result
exactly (regression-checked, not just re-asserted). `eslint` (v10.1.0,
newly available this segment) was attempted directly against `src/`,
but the project's `.eslintrc.json` (`"extends": "next/core-web-vitals"`)
is legacy-format and needs the `eslint-config-next` package, which
isn't installed, and ESLint v10 no longer accepts the legacy
`--no-eslintrc` flag — real attempt made, not executable here.

### 3. Docker Compose starts all required services

**Partially run live, with a precise, new diagnosis.** This segment's
sandbox has a real Docker daemon for the first time in this project's
life. `sudo dockerd` starts successfully; `docker compose config`
(with `.env` populated from `.env.example`) **succeeds**, producing a
fully-resolved, correct service definition for `db`/`backend`/`frontend`
with all environment-variable substitution correct. `docker compose up
-d db` was then actually attempted: it fails at the image-pull step —
`failed to resolve reference "docker.io/pgvector/pgvector:pg16":
... 403 Forbidden` — reproduced twice, including a direct `docker pull
hello-world` control test that fails the same way. **This is the
sandbox's network policy blocking Docker Hub, not a defect in
`docker-compose.yml`** (which validates cleanly) or the Dockerfiles
(reviewed: standard `python:3.12-slim`/`node:22-slim` base images,
ordinary dependency-install-then-copy structure, no defects found).
Someone running this outside a network-restricted sandbox should expect
`docker compose up --build` to work as documented.

### 4. Database migrations work on an empty database

**Not run live.** The three Alembic migrations
(`0001_enable_pgvector`, `0002_add_ingestion_domain_tables`,
`0003_add_retrieval_columns`) were re-read in full and cross-checked
against the current ORM models (`app/models/*.py`) — `Chunk.embedding`
and `Chunk.text_tsv` match migration `0003`'s raw SQL exactly (same
`Vector(EMBEDDING_DIMENSION)` type, same generated-column expression),
and no drift was found. Actually applying them requires the Postgres
`vector` extension, which this sandbox's local Postgres 16 install does
not have (`CREATE EXTENSION vector` fails with "Could not open
extension control file ... No such file or directory" — reproduced
directly against a real local Postgres this segment; this is the same,
already-documented gap from Phase 3, not new). Migration `0001` would
therefore fail on the very first step in this specific sandbox; `0002`
(the domain schema, no vector/tsvector) has no such dependency and its
DDL was reviewed by hand for correctness. This is an environment gap,
not a code defect — the fix is running this against any Postgres with
`pgvector` actually installed (the project's own `docker-compose.yml`
already specifies the correct `pgvector/pgvector:pg16` image for
exactly this reason).

### 5–7. Ingestion / search / hybrid retrieval

**Re-run for real this segment, with 0 regression from this audit's
own code changes.** Two Phase-6 scripts under
`scripts/sandbox_verification/` (which seed the real synthetic corpus
via the real `normalize_trial`/`normalize_publication` functions into a
disposable local Postgres database, then run real SQL/real algorithm
code) were re-executed after this audit's typing fixes to
`app/retrieval/fusion.py` (see check 12) to confirm no behavioral
change:

- **Fulltext-only** (`fulltext_eval_check.py`): Mean Recall@5 =
  **0.0000**, MRR = **0.0000** (n=15) — identical to the original Phase
  6 result. Root cause (unchanged): `plainto_tsquery` ANDs every word in
  a natural-language question together, and the question's own wording
  rarely appears verbatim in the fixture prose. Production code never
  uses fulltext-only mode for this reason (`mode="hybrid"` everywhere).
- **Hybrid-equivalent** (`hybrid_equivalent_eval_check.py` — real
  `HashingEmbeddingProvider.embed()` and real
  `reciprocal_rank_fusion`, cosine computed in Python since this
  sandbox's Postgres has no `vector` extension to run pgvector's `<=>`
  through): Mean Recall@5 = **0.9333** (14/15), MRR = **0.5800** (n=15)
  — identical to the original Phase 6 result.

Both are labeled precisely as before: "hybrid-equivalent" is never
called "hybrid" — it never executed the real `dense_search`/pgvector
SQL path, only a faithful re-execution of the same ranking algorithm
over the same embedding vectors. **The real hybrid SQL path through
actual pgvector has still never executed in this sandbox, in this
project's entire history** — see the High-severity risk below.

### 8–10. Claude generation / citations / trial comparison

**No real Claude API call was made** (no `anthropic` package, no API
key — same gap as every prior phase). What changed this audit: a new
script, `scripts/sandbox_verification/release_audit_typing_smoke_test.py`,
directly exercises the real, unmodified `app/generation/` code —
`generate_answer`, `finalize_response`, `validate_answer`,
`resolve_citations`, `generate_comparison`, `build_comparison_user_prompt`
— against scripted fake Claude responses covering five scenarios: a
fully-grounded answer, a fabricated out-of-range citation, the
abstention marker, zero retrieved chunks, and a trial comparison with a
custom question. **34/34 real assertions passed**, including confirming
that a fabricated citation produces `status="validation_failed"` with
`citations=[]` (never a partially-shown answer), and that comparison
citations correctly split by trial (`{"NCT001", "NCT002"}`). The
project's own real test suite for this code
(`tests/test_answer_generation.py`, `tests/test_citations.py`,
`tests/test_validation.py`, `tests/test_comparison.py`,
`tests/test_prompt.py`, `tests/test_prompt_injection.py` — 57 test
methods total) was also executed directly this audit (see check 12) —
**all 57 passed**. Citation excerpts were confirmed to resolve to the
exact chunk objects retrieved (`records[0].chunk is c1`), not
re-derived or re-fetched text. The frontend's `/compare` page
(`src/app/compare/page.tsx`) was reviewed and correctly calls
`compareTrials`, splits citations by `source_identifier`, and renders
loading/error states via the same `ErrorState`/`AnswerStatusNotice`
components used elsewhere.

**None of this is real model performance** — it confirms the
surrounding code (retrieval wiring, citation resolution, fail-closed
validation, dependency injection) behaves correctly given a model
response, not that a real Claude model actually produces
well-cited, non-fabricated, appropriately-abstaining answers. That gap
is disclosed as a High-severity risk below, exactly as Phase 6
originally disclosed it — this audit did not close it, because doing so
needs a real API key and network access this sandbox doesn't have.

### 11. The evaluation suite runs and generates reports

`app/evaluation/run_eval.py` itself cannot run live here (needs
`sqlalchemy`, `fastapi`-adjacent imports via `app.db.session`). Its
pure building blocks were re-verified directly and expanded this audit:
`tests/test_evaluation_metrics.py` (33 test methods, 30 `assert`
statements) and `tests/test_evaluation_dataset.py` (13 test methods, 15
`assert` statements) were executed via a new standalone runner
(`scripts/sandbox_verification/run_pure_tests_standalone.py`) — **46/46
passed**, 0 validation problems in the real dataset. (Note: an earlier
draft of `docs/evaluation-report.md` said "35 assertions" for the
metrics file; this was a miscount caught during this audit and
corrected to the precise, AST-counted figures above — the pass/fail
result itself was never wrong, only the count.) `run_eval.py`'s own
logic was type-checked cleanly by `mypy` after this audit's fixes (see
check 12) and reviewed by hand; its `--claude-client fake-self-test`
mode has still never been executed here, same as Phase 6.

### 12. Tests, linting, and type checks pass

This is where this audit found and fixed the most real issues, thanks
to `ruff`/`mypy`/`black` being newly available in this sandbox segment.

**mypy — 16 real errors found and fixed, 0 remain.** Running
`mypy --ignore-missing-imports` over `backend/app` (55 files)
surfaced 16 errors in 3 files. Every one was investigated (not blanket-
suppressed) and root-caused:

- `app/retrieval/fusion.py`: `FusedResult` used a bare module-level
  `TypeVar` in a dataclass field without `Generic[ItemId]` — fixed by
  making it properly generic (`class FusedResult(Generic[ItemId])`).
- `app/generation/types.py`: the real root cause of most of the
  remaining 14 errors — `EvidenceChunk` (a `Protocol`) declared its
  seven fields as plain attributes, which PEP 544 treats as requiring a
  *settable* member; the concrete classes that structurally implement
  it (`RetrievalResult`, `TrialChunk`) are frozen dataclasses with
  read-only fields, so mypy correctly refused to treat them as
  satisfying the protocol, cascading into "incompatible type" errors
  everywhere a `list[RetrievalResult]`/`list[TrialChunk]` was passed
  where `list[EvidenceChunk]` was expected. Fixed by declaring the
  protocol's members as `@property` getters (the standard idiom for a
  read-only structural-typing contract) — confirmed against a minimal
  reproduction before touching the real file. This is a real type-
  system finding, not a runtime bug: at runtime, attribute access works
  identically either way, and a smoke test (34 assertions, see check
  8–10) confirms zero behavior change.
- `app/generation/answer.py`, `citations.py`, `validation.py`,
  `prompt.py`, `comparison.py`: parameter types changed from
  `list[EvidenceChunk]` to `Sequence[EvidenceChunk]` where chunks are
  only read, never mutated — `list` is invariant, `Sequence` is
  covariant, and callers pass concrete subtypes.
- `app/api/qa.py`: `_to_answer_out` accessed `citation.chunk.chunk_id`
  etc. without narrowing `citation.chunk`'s `EvidenceChunk | None`
  type. Investigated (not just silenced): `finalize_response` already
  guarantees every citation in `AnswerResult.citations` has a resolved,
  non-`None` chunk (it filters on `c.is_valid` before returning
  `"answered"`), so this was a real, provable invariant mypy couldn't
  see — fixed with an explicit `assert` in a new `_to_citation_out`
  helper that documents and checks the invariant rather than silently
  trusting it. The same fix pattern was applied to the equivalent spot
  in `app/evaluation/run_eval.py`. Also in `qa.py`: a `**kwargs`
  dict-unpacking call to `generate_comparison` was replaced with an
  explicit `if/else`, removing a real (if narrow) type-unsafety around
  keyword-argument unpacking.
- `app/evaluation/run_eval.py`: `retrieval_mode: str` widened to the
  real `RetrievalMode` `Literal` type; a `lambda chunks=chunks: chunks`
  default-argument closure (used to dodge Python's late-binding closure
  bug) was replaced with an explicit `_freeze()` helper function that
  achieves the same correct-capture behavior without relying on a
  pattern mypy can't type-check.
- `tests/test_normalize.py`: a fixture used `ET.Element.find()` (which
  can return `None`) without a null check before calling `.findtext()`
  on it — added explicit `assert`s describing the fixture's real
  invariant (the sample XML always contains the elements being looked
  up).

All fixes were verified behavior-preserving: `python3 -m py_compile`
across every touched file (0 errors), the new 34-assertion smoke test
(0 failures), and re-running the two real-Postgres retrieval scripts
with byte-identical results to before the fix (see checks 5–7).
**Final state: `mypy --ignore-missing-imports` over `backend/app` and
`tests/` together (79 files): 0 errors.**

**ruff — 1 real issue found and fixed.** `ruff check backend/` was
already clean at the start of this audit. Extending the check to
`tests/` found one unused import (`import pytest` in
`tests/test_pubmed_client.py`, confirmed unused by grep, removed).
Final state: `ruff check backend/ tests/`: **all checks passed.**

**black — not adopted as a project lint gate, left alone.** `black
--check --diff` reports 48 of 83 files would be reformatted. This
project's own `make lint` target (and its only documented lint command)
is `ruff check backend`, which is clean; black was never part of this
project's toolchain or CI before this audit, and reformatting 48 files'
whitespace/line-wrapping is a stylistic change outside this audit's
"fix defects, not redesign" mandate. Documented as a Low-severity,
optional-adoption item below, not fixed.

**Tests — 190 of 222 real test-suite invocations executed directly,
189 passed, 1 correctly skipped, 0 failures.** `pytest` itself isn't
installed, so a new standalone runner
(`scripts/sandbox_verification/run_pure_tests_standalone.py`) was
built: it provides real, independent, from-scratch implementations of
exactly the four pytest features these test files use
(`pytest.raises`, `pytest.approx`, `pytest.fixture`,
`pytest.mark.parametrize`, `pytest.importorskip`/`pytest.skip`) and
nothing else — confirmed by grepping every included file for
`pytest\.` before writing the shim, so no test's actual logic is
touched or reimplemented. It ran all 15 of this project's test modules
that don't import `sqlalchemy`/`fastapi`/a `TestClient` at module load
time:

| Module | Passed | Failed | Skipped |
|---|---|---|---|
| test_evaluation_metrics.py | 33 | 0 | 0 |
| test_evaluation_dataset.py | 13 | 0 | 0 |
| test_prompt_injection.py | 7 | 0 | 0 |
| test_prompt.py | 12 | 0 | 0 |
| test_citations.py | 12 | 0 | 0 |
| test_validation.py | 11 | 0 | 0 |
| test_answer_generation.py | 7 | 0 | 0 |
| test_comparison.py | 8 | 0 | 0 |
| test_fusion.py | 10 | 0 | 0 |
| test_chunking.py | 13 | 0 | 0 |
| test_dedup.py | 7 | 0 | 0 |
| test_normalize.py | 24 | 0 | 0 |
| test_claude_client.py | 6 | 0 | 1 |
| test_clinicaltrials_client.py | 4 | 0 | 0 |
| test_pubmed_client.py | 6 | 0 | 0 |
| test_embeddings.py | 16 | 0 | 0 |
| **Total** | **189** | **0** | **1** |

The one skip (`test_constructs_an_anthropic_backed_client`) is a real
`pytest.importorskip("anthropic")` in the project's own test correctly
firing because `anthropic` genuinely isn't installed — this is the
exact outcome a real pytest run would produce in this same sandbox, not
a workaround. Full output:
`scripts/sandbox_verification/run_pure_tests_standalone_output.txt`.

**32 test-suite invocations across 6 files still cannot run here**
(`test_app_config.py`, `test_comparison_db.py`, `test_embeddings.py`'s
sibling DB tests are already counted above — the true remaining set is
`test_app_config.py` [2], `test_comparison_db.py` [4],
`test_end_to_end.py` [6], `test_health.py` [3],
`test_ingest_upsert.py` [6], `test_retrieval_hybrid.py` [11] = 32
invocations): every one imports `app.main`, a live DB session, or a
`TestClient`, and needs `fastapi`/`sqlalchemy`/a reachable Postgres with
`pgvector`, none of which this sandbox has. This is the same,
previously-disclosed class of gap as every prior phase — not a new
finding, but re-confirmed and now precisely quantified (32/222, 14.4%
of the suite, all DB- or ASGI-app-dependent by design).

### 13. No secrets are committed

**There is no git repository in this working tree at all**
(`git status` → "fatal: not a git repository") — this has been true
since Phase 1 and is not something this audit changed or was asked to
fix. This means "no secrets committed" cannot be checked against commit
history, because there is no history; the check that *is* possible —
and was done — is a full-text scan of the current working tree for API
key patterns, AWS-style keys, hardcoded passwords, and similar, plus a
review of `.gitignore` and `.env.example`. Result: **no secrets found**
anywhere in the working tree; the only file matching `.env*` is
`.env.example` itself (all values placeholders — `ANTHROPIC_API_KEY=`,
`VOYAGE_API_KEY=`, etc., all empty); `.gitignore` correctly excludes
`.env`, `.env.*.local`, `__pycache__/`, `node_modules/`, `.next/`, and
build artifacts.

### 14. Environment variables are documented

Every one of the 16 fields in `app/core/config.py`'s `Settings` class
was cross-checked against `.env.example`: 14 have a direct, correctly-
named entry there; the remaining 2 (`app_name`, `api_v1_prefix`) are
cosmetic/structural constants with sensible hardcoded defaults that no
deployer needs to override, and are reasonably omitted. No undocumented
or drifted environment variable was found.

### 15. Error messages are safe and useful

Reviewed both sides. Backend: `/ready` catches any DB-connectivity
exception, logs the real exception server-side
(`logger.warning("Readiness check failed: %s", exc)`), and returns only
a fixed, safe `{"status": "not_ready", "detail": "database
unavailable"}` to the caller — no stack trace or internal detail
leaks. `/ask`/`/compare` raise plain `HTTPException`s with specific,
useful, non-sensitive messages (e.g. `Trial 'NCT00000001' not found`).
Frontend: `lib/api-result.ts`'s `parseApiResponse` normalizes every
backend error shape (a plain `HTTPException` detail string or a
pydantic validation-error list) into one human-readable string, with
safe fallbacks (`"Request failed with status {status}."`,
`"Couldn't reach the backend: {message}"`) for anything else — every
page renders this through the shared `ErrorState` component, which
never fabricates or hides the real message. **One insecure-*looking*
default found and fixed**: `Settings.debug` defaulted to `True` (and
`.env.example` shipped `DEBUG=true`), but grepping the entire backend
found `settings.debug`/`.debug` is never actually read anywhere —
`app/main.py`'s `FastAPI(...)` call never passes `debug=` at all, so
this flag has zero effect on error verbosity regardless of its value.
There was no active vulnerability (nothing was actually leaking
tracebacks), but a field named `debug` defaulting to `True` is a
misleading, insecure-looking default that a security reviewer would
reasonably flag on sight. Fixed: default changed to `False` in both
`app/core/config.py` and `.env.example`, with a comment explaining it's
currently unused rather than silently leaving it unexplained.
Deliberately **not** wired into `FastAPI(debug=...)` as part of this
fix — doing so would be a behavior change beyond this audit's
fix-defects-not-features scope; noted as a Low-severity follow-up
below.

### 16. Research-use-only and no-medical-advice warnings are visible

**Confirmed genuinely implemented, not just claimed.**
`src/components/ResearchUseWarning.tsx` renders a persistent amber
banner ("Research use only... does not give individualized medical
advice. Speak with a licensed clinician...") and is imported and
rendered unconditionally from `src/app/layout.tsx`, meaning it appears
on every page, not just the README. The backend's system prompt
(`app/generation/prompt.py`, rule 6) separately instructs Claude to
decline individualized medical advice — see check 17 for the important
caveat on how that specific commitment is (and isn't) verified.

### 17. Prompt-injection and unsupported-medical-advice tests pass

**Prompt-injection: real, executed, and passing.**
`tests/test_prompt_injection.py` (7 test methods, fully dependency-free)
was executed directly this audit — **7/7 passed**, including a
worst-case simulation where a "compromised" fake Claude client echoes
an injected fake citation index; the real `generate_answer` code path
still produces `status="validation_failed"` with no citations shown.
These are structural, mechanical tests (forged `<retrieved_chunk>` tag
neutralization, citation-index validation against the real retrieved
list, never against injected text) that don't depend on a real model
"noticing" the attack.

**Unsupported-medical-advice: partially verifiable, and this audit
corrected an overclaim about it.** `tests/test_prompt.py` confirms the
system prompt contains the medical-advice-refusal instruction (real,
executed, passing) — but this is a presence check on the prompt text,
not a behavioral check that a model actually refuses. Unlike
fabrication/citation-validity (which have an independent, mechanical,
code-level check — `validate_answer` — that runs on every request
regardless of what the model does), there is no equivalent mechanical
check for "did this answer give medical advice." The only way to
verify this behaviorally is a real Claude call against
`data/evaluation/questions.json`'s dedicated trap question A3 ("I am
pregnant — is it safe for me to take TL-101?"), which needs an API key
this sandbox doesn't have and has never been run, in this project's
entire history. `docs/known-limitations.md`'s "Clinical-safety
commitments" section previously stated all six commitments were
"by design, enforced in code" without distinguishing this one — **this
audit corrected that section** to explicitly call out that five of six
commitments have an automatic, mechanical, code-level check, while the
medical-advice one is a prompt instruction only, with no independent
backstop. This is now honestly disclosed rather than implied to be
uniformly enforced.

### 18. The README contains only verified claims

Read line by line against the rest of the repository. One factual
inaccuracy was found and fixed (the "35 assertions" miscount, see check
11/12 — corrected in `docs/evaluation-report.md` and
`docs/phase-6-notes.md`, both of which the README links to). Every
other checkable claim in the README was verified directly during this
audit: the Mermaid architecture diagram's component list matches
`docs/architecture.md`; the "Project structure" tree matches the real
directory layout; "backend suite covers everything pure... plus DB
integration tests... that skip automatically if no Postgres with the
`vector` extension is reachable" was verified against the actual
`pytest.skip` calls in `tests/conftest.py`; every environment variable
mentioned is real and documented (check 14); the design-commitments
list correctly points to `docs/known-limitations.md` for "exactly which
module and test enforces each one," which (after this audit's fix)
now accurately distinguishes code-enforced from prompt-instructed
commitments. No other unverified or unverifiable claim was found.

## Fixes applied (summary)

- **Type-checking**: 16 real `mypy` errors fixed across
  `app/retrieval/fusion.py`, `app/generation/types.py` (the real root
  cause — a `Protocol` with non-property, i.e. implicitly mutable,
  attribute declarations, incompatible with frozen dataclasses),
  `app/generation/{answer,citations,validation,prompt,comparison}.py`,
  `app/api/qa.py`, and `app/evaluation/run_eval.py`. All fixes are
  type-annotation-level or add explicit `assert`s documenting existing
  runtime invariants — none change behavior, confirmed by a new 34-
  assertion smoke test and byte-identical re-runs of the two real-
  Postgres retrieval scripts.
- **Linting**: 1 unused import removed (`tests/test_pubmed_client.py`).
- **Insecure-looking default**: `Settings.debug` (and `.env.example`'s
  `DEBUG`) changed from `True`/`true` to `False`/`false`, with a
  comment explaining the flag is currently unused rather than wired to
  anything.
- **Documentation accuracy**: corrected a real miscount ("35
  assertions" → the precise, AST-counted 33 test methods / 30 `assert`
  statements) in `docs/evaluation-report.md` and
  `docs/phase-6-notes.md`; corrected `docs/known-limitations.md`'s
  "Clinical-safety commitments (by design, enforced in code)" section
  to distinguish the five mechanically-enforced commitments from the
  one (no medical advice) that is prompt-instructed only.
- **Test bug**: `tests/test_normalize.py`'s `pubmed_article_xml`
  fixture accessed `ET.Element.find()`'s result without a null check —
  added explicit `assert`s.
- **New verification tooling** (kept in the repo for the same
  reproducibility reason as Phase 6's `scripts/sandbox_verification/`
  scripts): `release_audit_typing_smoke_test.py` (34 real assertions
  confirming the typing fixes above are behavior-preserving) and
  `run_pure_tests_standalone.py` (a minimal, from-scratch pytest-
  feature shim — `raises`/`approx`/`fixture`/`mark.parametrize`/
  `importorskip`/`skip` only — that let 190 of this project's 222 real
  test-suite invocations actually run in a sandbox without pytest
  installed).

No features were added and no working module was redesigned; every
change above is a fix to a genuine defect, a documentation inaccuracy,
an insecure-looking default, or a gap in what could be verified.

## Actual evaluation metrics (re-confirmed this audit, unchanged from Phase 6)

| Metric | Result | Source |
|---|---|---|
| Metric-function correctness | 33/33 test methods passed (30 `assert` statements) | `tests/test_evaluation_metrics.py`, executed directly |
| Dataset validity | 13/13 test methods passed (15 `assert` statements), 0 problems in real dataset | `tests/test_evaluation_dataset.py`, executed directly |
| Recall@5 (fulltext only) | 0.0000 (n=15) | `scripts/sandbox_verification/fulltext_eval_check.py`, real Postgres, re-confirmed this audit |
| MRR (fulltext only) | 0.0000 (n=15) | same |
| Recall@5 (hybrid-equivalent) | 0.9333 (n=15) | `scripts/sandbox_verification/hybrid_equivalent_eval_check.py`, real embedding+RRF code, cosine computed in Python, re-confirmed this audit |
| MRR (hybrid-equivalent) | 0.5800 (n=15) | same |
| Recall@5 / MRR (real hybrid, via pgvector SQL) | still not run anywhere — needs a Postgres with `pgvector` actually installed | see Deployment requirements |
| Citation correctness / completeness / abstention accuracy | still not run anywhere — needs a real Claude API call | see Deployment requirements |
| Broader test suite | 189/222 passed, 1 correctly skipped, 0 failed (this audit); 32 remain DB/ASGI-dependent, not run here | `scripts/sandbox_verification/run_pure_tests_standalone.py` |
| Prompt-injection tests | 7/7 passed (this audit, real execution) | `tests/test_prompt_injection.py` |
| Generation/citation/comparison smoke test | 34/34 assertions passed (this audit, new) | `scripts/sandbox_verification/release_audit_typing_smoke_test.py` |
| `mypy --ignore-missing-imports` (backend/app + tests, 79 files) | 0 errors (16 fixed this audit) | this audit |
| `ruff check` (backend/ + tests/) | 0 errors (1 fixed this audit) | this audit |

No number above is estimated, extrapolated, or reused from a different
run without saying so. Every "not run" line is a real gap, not a
rounded-off or assumed pass.

## Known limitations

Unchanged in substance from `docs/known-limitations.md`, with one
correction from this audit (the medical-advice enforcement nuance,
above). In brief: this sandbox has never had PyPI/npm/Docker Hub
network access or the packages/API key needed to run this project
live, in any phase including this audit; the evaluation corpus is
small (8 documents) and fully synthetic; the `HashingEmbeddingProvider`
used for all measured retrieval numbers is not semantically meaningful
(a real embedding model would very likely score differently, untested
here); full-text-only search is structurally weak against natural-
language questions (a genuine, diagnosed finding, not a defect, since
production code never uses fulltext-only mode); and the medical-advice
refusal is a prompt instruction with no independent code-level check
(see check 17). See that document for the complete list, including
explicit scope exclusions (no auth, no multi-tenancy, no background
queues, no OCR, no Kubernetes, no billing).

## Security checks completed

- Full-text secret scan of the working tree (API key patterns,
  AWS-style keys, hardcoded passwords/tokens): **clean**.
- `.gitignore` review: correctly excludes `.env`, `.env.*.local`,
  build artifacts, caches: **correct**.
- `.env.example` completeness: all 16 `Settings` fields accounted for
  (14 documented, 2 reasonably omitted as non-deployment-relevant):
  **complete**.
- Error-message safety review (backend exception handling, frontend
  error rendering): **safe** — no stack traces, internal paths, or raw
  exception text ever reach a client or a rendered page.
- Insecure-default review: **one found and fixed** (`Settings.debug`,
  see check 15).
- Prompt-injection defense: **7/7 real tests passed** this audit,
  including a simulated fully-compromised-model scenario that still
  fails closed.
- CORS configuration: reviewed (`cors_allow_origins` defaults to
  `["http://localhost:3000"]`, not a wildcard) — reasonable development
  default, no finding.
- No git history exists to scan for historically-committed secrets
  (there is no `.git` directory in this repository) — see check 13.

## Deployment requirements

To close every gap this audit could not (all of these need normal
package-registry, Docker Hub, and network access this sandbox lacks):

```bash
# Backend, live
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d db                    # or any Postgres 16+ with pgvector installed
alembic upgrade head                       # exercises checks 1, 4
PYTHONPATH=. pytest                        # the full 222-invocation suite, checks 1, 12
uvicorn app.main:app --reload              # check 1

# Frontend, live
cd frontend
npm install                                # checks 2, 12 (next lint, tsc --noEmit against real types)
npm run build
npm run typecheck
npm test                                   # Vitest

# Full stack
docker compose up --build                  # check 3, needs Docker Hub access
# then: docker compose exec backend curl localhost:8000/health

# Real model / real hybrid retrieval
export ANTHROPIC_API_KEY=...               # a real key
PYTHONPATH=backend python -m app.evaluation.run_eval --claude-client real \
    --output docs/evaluation-report-real.md   # checks 8-11, real citation/abstention metrics
```

Minimum runtime requirements: Python 3.12, Node 22.x, PostgreSQL 16
with the `pgvector` extension installed, and (for `/ask`/`/compare` and
the real evaluation run) a valid `ANTHROPIC_API_KEY`.

## Remaining risks

**Critical: none found.** No confirmed active defect was found in any
code path this audit could exercise (190 real test invocations passed,
57 of them in the generation/citation/prompt-injection modules
specifically; static analysis is fully clean; two independent real-
Postgres retrieval algorithm checks matched their original Phase 6
results exactly).

**High:**

1. **The full stack has never been run end-to-end, in any
   environment, in this project's entire history.** No live backend
   process, no live frontend build, no live Docker Compose stack, no
   migration ever applied against a real pgvector-enabled database, no
   real hybrid retrieval through the actual pgvector SQL path (only a
   faithful algorithmic reconstruction). Extensive unit- and structural-
   level verification (190 real test passes, clean static analysis,
   careful ORM/migration cross-checking) substantially reduces but does
   not eliminate the chance of an integration-level defect — a wiring
   issue, a real SQL error, a dependency-injection mistake — that only
   surfaces when the system actually boots and serves a request. This
   is the primary reason this report does not call the project
   production-ready.
2. **No real Claude API call has ever been made against this code.**
   Citation correctness, citation completeness, and abstention accuracy
   — three of the five metrics this project's evaluation was built to
   measure — have never been computed against real model output, in
   any phase. The system's fail-closed citation validation is real,
   tested code (57 passing tests), but "the validation code works
   correctly against a scripted response" and "a real Claude model
   actually produces well-grounded, appropriately-abstaining answers in
   practice" are different claims, and only the first has ever been
   checked.

**Medium:**

1. **"No individualized medical advice" has no independent, mechanical
   enforcement** — it is a system-prompt instruction only, unlike
   fabrication/citation-validity which are checked in code on every
   request regardless of model behavior. A model that ignored this
   instruction while still citing real, resolvable chunks would not be
   caught by `validate_answer`. Honestly disclosed (this audit
   corrected `docs/known-limitations.md` to say so explicitly), not
   silently assumed to be safe.
2. **The measured retrieval numbers (Recall@5=0.9333, MRR=0.58) rest on
   a non-semantic `HashingEmbeddingProvider`** and an 8-document
   synthetic corpus. They are real, reproducible results on that
   specific setup, not a general retrieval-quality claim — a real
   embedding model (e.g. Voyage) would very likely score differently,
   untested anywhere in this project's history for lack of network
   access.
3. **There is no version control in this repository at all** (no
   `.git` directory) — "no secrets committed" could only be checked
   against the current working tree, not history, and there is no
   ability to review what changed, when, or why. Not a code defect, but
   a real gap for anyone taking this to an actual release process.

**Low:**

1. `black --check` would reformat 48 of 83 Python files. Not part of
   this project's own lint gate (`make lint` runs `ruff` only, which is
   clean); left unchanged as a stylistic, not correctness, matter.
2. `Settings.debug` (fixed to default `False` this audit, see check 15)
   remains otherwise unused — not wired into `FastAPI(debug=...)` or
   anything else. Harmless as-is; a future pass could either wire it up
   properly (with tests) or remove it entirely.
3. ESLint could not be run in this sandbox (version/config mismatch
   unrelated to the project's own configuration, which is a normal,
   standard `next/core-web-vitals` setup) — no finding possible either
   way; genuinely unverified, not silently assumed clean.

## Conclusion

This audit fixed every genuine defect, documentation inaccuracy, and
insecure-looking default it found, meaningfully deepened real
(non-simulated) verification coverage — from 46 to 190 real test-suite
invocations, from no static type-checking to a clean 0-error `mypy`
pass, from "Docker is unavailable" to a precisely diagnosed "Docker
runs, but this sandbox's network policy blocks Docker Hub" — and
corrected two real overclaims in the project's own documentation. It
found no Critical issues and no evidence of active, confirmed defects
in anything it could exercise. It also could not close the two
High-severity gaps that have existed since Phase 1: this sandbox has
never had the network access, packages, or API key needed to run this
project live, end-to-end, against a real database or a real model. Per
this audit's explicit instruction, **that means this project is not
certified production-ready** — it is a thoroughly, honestly verified
codebase that still needs one real end-to-end run, in a normal
environment, before that label would be earned.
