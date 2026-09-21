# Evaluation Report

This report covers Phase 6's evaluation deliverable: a 20-question
ground-truth set, Recall@5, MRR, citation correctness, citation
completeness, and abstention accuracy. Per the explicit instruction this
phase was built under ("do not invent metrics; report actual results and
remaining issues"), every number below states exactly how it was
produced and whether it came from real execution in the sandbox that
built this project, a faithful-but-not-identical real execution, or
requires the reader's own environment. Nothing here is estimated or
guessed.

## The evaluation corpus and dataset

`data/evaluation/fixtures_ctgov.json` (5 synthetic trials) and
`fixtures_pubmed.xml` (3 synthetic publications) describe fictional
drugs ("TL-101", "TL-205") and conditions, shaped exactly like real
ClinicalTrials.gov/PubMed API responses. This was necessary, not just
convenient: the sandbox that built this project has no network access to
ClinicalTrials.gov or PubMed (see `docs/known-limitations.md`), so any
ground truth against real trial data would have had to be invented
rather than derived from the documents themselves. A synthetic corpus
with facts the report's author wrote and can point to directly is the
only way to get ground truth that is verifiably not fabricated.

`data/evaluation/questions.json` has 20 questions: 15 answerable (with a
curated `relevant_source_identifiers` ground-truth list per question,
including one deliberately multi-source question) and 5 "trap" questions
the system should abstain on — a nonexistent trial ID, a condition never
studied in this corpus, an individualized-medical-advice request, an
outcome never reported for the referenced drug, and a topic never
discussed. Every fixture document, and the reasoning behind every
question's ground truth, is documented inline in those two files.

**Real, executed verification of the dataset itself:**
`tests/test_evaluation_dataset.py` was executed directly (see
"What actually ran" below) and confirmed, against the real fixture
files: exactly 20 questions, exactly 15 answerable and 5 traps, no
duplicate IDs, every `relevant_source_identifiers` value resolves to an
identifier that the real `normalize_trial`/`normalize_publication`
functions actually produce from the fixture files, and — a coverage
property specific to this dataset — every one of the 8 fixture documents
is ground truth for at least one answerable question.

## What actually ran in the sandbox that built this project, and how

This sandbox has no network access to PyPI/npm/Docker Hub/the system
package archive, and no `anthropic` package, `API` key, `sqlalchemy`,
`fastapi`, `pytest`, or Python Postgres driver (`psycopg`/`psycopg2`) —
see `docs/known-limitations.md` for the full, re-confirmed list. It does
have a real local PostgreSQL 16 server. Three genuinely different kinds
of verification were possible given that:

### 1. Pure metric functions — executed directly, in full

`backend/app/evaluation/metrics.py`'s `recall_at_k`, `reciprocal_rank`,
`mean_recall_at_k`, `mean_reciprocal_rank`, `citation_correctness`,
`citation_completeness`, `abstention_accuracy`, and
`abstention_confusion_counts` need no database, network, or third-party
package. All 33 test methods (30 `assert` statements; some methods
assert more than one thing) in `tests/test_evaluation_metrics.py` were
executed directly with a standalone Python runner
(`scripts/sandbox_verification/run_pure_tests_standalone.py` — pytest
itself isn't installed, so this runner supplies minimal, independent
implementations of the exact two pytest features these tests use,
`pytest.raises`/`pytest.approx`, and nothing else) and **all 33
passed**. (An earlier draft of this report said "35 assertions" — that
was a miscount caught during the release-hardening audit; re-run with
an AST-based counter, this file has 33 test methods and 30 `assert`
statements, not 35, and the pass/fail result is unchanged: 0 failures
either way.)

### 2. Dataset validation against the real corpus — executed directly, in full

`backend/app/evaluation/dataset.py`'s `load_questions`/`validate_questions`
also need no third-party package. All 13 test methods (15 `assert`
statements) in `tests/test_evaluation_dataset.py` were executed
directly (same standalone runner) against the real
`data/evaluation/*.json`/`*.xml` files (ground truth resolved via the
real `normalize_trial`/`normalize_publication` functions, not a mock)
and **all 13 passed**, with **zero validation problems** found in the
real dataset.

### 3. Retrieval math against a real Postgres — executed directly, with two clearly-labeled variants

Neither `sqlalchemy` nor any Python Postgres driver is installed, so the
real `app/retrieval/*.py` modules (which use SQLAlchemy) could not be
imported or executed as-is. Instead, two standalone scripts under
`scripts/sandbox_verification/` re-created the same SQL/algorithms by
hand, calling the real, unmodified `app.ingestion.normalize`,
`app.retrieval.embeddings.HashingEmbeddingProvider`,
`app.retrieval.fusion.reciprocal_rank_fusion`, and
`app.evaluation.metrics` functions directly wherever possible, and
shelling out to `psql` for the SQL this sandbox's Postgres *can* run.

**Fulltext-only** (`scripts/sandbox_verification/fulltext_eval_check.py`):
seeds the real fixture corpus (via `normalize_trial`/`normalize_publication`)
into a disposable Postgres database, runs the exact SQL
`app/retrieval/fulltext.py`'s `fulltext_search` uses
(`ts_rank`/`plainto_tsquery`), and computes Recall@5/MRR with the real
metric functions.

> **Result: Mean Recall@5 = 0.0000, MRR = 0.0000 (n = 15 answerable
> questions).** Full per-question output in
> `scripts/sandbox_verification/fulltext_eval_check_output.txt`.

This is a real, reproducible zero — and a genuinely useful finding, not
just a null result. `plainto_tsquery` ANDs every content word in the
query together; a diagnostic check confirmed that stripping a
question down to only the words that literally appear in its target
document (e.g. "primary endpoint TL-101 met" instead of "What is the
primary endpoint of the **trial** **NCT90000001**, and was it met?")
matches with `ts_rank` 0.71, while the full natural-language question
matches nothing, because the word "trial" and the echoed NCT/PMID
identifier essentially never appear verbatim inside the fixture
documents' own prose. Since this affected nearly every one of the 15
questions, it's not particular to one bad question — it's a structural
property of full-text-only search against natural-language questions
that this project's own design already anticipated: **every real
endpoint (`/ask`, `/retrieve`'s default, every frontend page) uses
`mode="hybrid"`, never fulltext alone**, specifically so dense retrieval
can compensate for exactly this kind of word-choice mismatch. See
`docs/known-limitations.md` for the fuller writeup.

**Hybrid-equivalent** (`scripts/sandbox_verification/hybrid_equivalent_eval_check.py`):
adds the dense half using the *real* `HashingEmbeddingProvider.embed()`
and the *real* `reciprocal_rank_fusion`, but computes cosine similarity
in plain Python instead of via pgvector's `<=>` SQL operator (which this
sandbox's Postgres cannot run — the `vector` extension's control file is
absent). Cosine similarity is arithmetic over the same vectors either
way, so this is a faithful re-execution of the real ranking algorithm,
not a different one — but it did not go through the real
`dense_search`/pgvector SQL path, so it is reported as
**"hybrid-equivalent," never as "hybrid."**

> **Result: Mean Recall@5 = 0.9333 (14/15), MRR = 0.5800 (n = 15).**
> Full per-question output in
> `scripts/sandbox_verification/hybrid_equivalent_eval_check_output.txt`.

Read this calibrated, not at face value: the fixture corpus has only 8
total documents, so even a *random* ranking would put the one relevant
document in the top 5 about 5/8 = 62.5% of the time, and would score an
MRR around 0.34 (expected value of 1/rank for a uniformly-random
position among 8 items). The measured 93.3%/0.58 are both meaningfully
above that chance baseline, which is real evidence that the fused
ranking carries signal beyond corpus-size luck — but with only 8
documents this cannot be read as "93% retrieval accuracy" in any general
sense; it is a real result on a very small, synthetic corpus, no more
and no less. The one miss was Q8 ("What grade 3 or higher adverse event
rate was reported in the published results for TL-101?", relevant
document ranked outside the fused top 5).

### 4. Everything requiring a real Claude API call, real pgvector SQL, or the full pytest suite — not run here

Citation correctness, citation completeness, and abstention accuracy all
require grading a real generated answer, and there is deliberately no
dependency-free fake answer-generation provider in this project (see
`app/generation/client.py`'s docstring — a fake LLM response would
defeat the point of grounded generation). `backend/app/evaluation/run_eval.py`
is written and ready, including a `--claude-client fake-self-test` mode
that swaps in a scripted client (`ScriptedFakeClaudeClient`) purely to
prove the harness's own plumbing (seeding → indexing → retrieval →
generation → citation extraction → metric computation → Markdown report)
is wired correctly end to end — **its citation/abstention numbers, if
you run that mode, are not real model performance and the report it
produces says so explicitly** (`EvaluationReport.notes`). Getting real
citation correctness/completeness/abstention-accuracy numbers, a real
end-to-end pytest run (`tests/test_end_to_end.py`), and real
hybrid/dense Recall@5/MRR through the actual pgvector SQL path all need
the commands below, run somewhere with normal package access:

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Start Postgres 16 with pgvector (docker-compose.yml already uses the
# pgvector/pgvector:pg16 image):
docker compose up -d db

cd ..
PYTHONPATH=backend pytest                       # full suite, including test_end_to_end.py
PYTHONPATH=backend python -m app.evaluation.run_eval --claude-client real \
    --output docs/evaluation-report-real.md     # needs ANTHROPIC_API_KEY set
```

## Summary table

| Metric | Real result from this sandbox | Source |
|---|---|---|
| Metric-function correctness | 33/33 test methods passed (30 `assert` statements) | `tests/test_evaluation_metrics.py`, executed directly |
| Dataset validity | 13/13 test methods passed (15 `assert` statements), 0 problems in real dataset | `tests/test_evaluation_dataset.py`, executed directly |
| Recall@5 (fulltext only) | 0.0000 (n=15) | `scripts/sandbox_verification/fulltext_eval_check.py`, real Postgres |
| MRR (fulltext only) | 0.0000 (n=15) | same |
| Recall@5 (hybrid-equivalent) | 0.9333 (n=15) | `scripts/sandbox_verification/hybrid_equivalent_eval_check.py`, real embedding+RRF code, cosine computed in Python |
| MRR (hybrid-equivalent) | 0.5800 (n=15) | same |
| Recall@5 / MRR (real hybrid, via pgvector SQL) | not run here — needs pgvector | see commands above |
| Citation correctness | not run here — needs a real Claude API call | see commands above |
| Citation completeness | not run here — needs a real Claude API call | see commands above |
| Abstention accuracy | not run here — needs a real Claude API call | see commands above |
| End-to-end API test (`tests/test_end_to_end.py`) | written, reasoned through, syntax-verified (`py_compile`/`ast.parse`); not executed — needs `fastapi`/`sqlalchemy`/`pgvector` | see commands above |

## Remaining issues

- The one genuinely negative, real finding: full-text-only search is
  largely unusable against natural-language questions in this project's
  current form, because of `plainto_tsquery`'s AND semantics. This
  doesn't affect production behavior (hybrid mode is always used), but
  it's worth knowing if anyone considers using `mode="fulltext"`
  directly, or building a keyword-only fallback.
- The hybrid-equivalent result used the weak, non-semantic
  `HashingEmbeddingProvider` — a real semantic embedding model (e.g.
  Voyage, via `EMBEDDING_PROVIDER=voyage`) would very likely do better,
  but that has not been measured, here or anywhere, since it needs
  network access this sandbox never had.
- No number in this report reflects real Claude model behavior. Every
  citation-quality and abstention-quality claim this project makes
  structurally (see `docs/known-limitations.md`'s "clinical-safety
  commitments") is enforced by code that was reviewed and, where
  possible, exercised with a scripted fake — but "the fail-closed
  validation code runs correctly against a scripted answer" and "a real
  Claude model actually behaves this way in practice" are different
  claims, and only the first one has been checked here.
- The corpus size (8 documents, 3 of them near-duplicates in the same
  therapeutic area) limits how much the hybrid-equivalent Recall@5/MRR
  numbers can be trusted as a general quality signal, as described
  above. A larger, still-synthetic corpus (dozens of documents across
  more distinct topics) would make Recall@5/MRR far more discriminating
  and is a natural next step before drawing any real conclusion about
  retrieval quality.
