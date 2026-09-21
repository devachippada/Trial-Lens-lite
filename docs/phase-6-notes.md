# Phase 6 notes

What Phase 6 built: a 20-question evaluation dataset over a synthetic,
clearly-labeled fixture corpus; Recall@5, MRR, citation correctness,
citation completeness, and abstention-accuracy metrics as pure, tested
functions; an evaluation harness (`app/evaluation/`) that reuses the
real ingestion/retrieval/generation code rather than reimplementing it;
a `Depends()`-based dependency-injection refactor to the API layer so a
real end-to-end test can override the one dependency this project can
never fake for real (the Claude API call); that end-to-end test;
Docker deployment instructions; a portfolio-quality README rewrite; a
Mermaid architecture diagram; and known-limitations/clinical-safety
documentation. This is the final phase — see `docs/evaluation-report.md`
for exactly what ran and what didn't, and `docs/known-limitations.md`
for the full limitations/safety writeup this phase produced.

## Judgment calls worth flagging

**The evaluation corpus is fully synthetic, and that was a forced
choice, not a preference.** This sandbox has no network access to
ClinicalTrials.gov or PubMed (unchanged since Phase 2), so there was no
way to fetch real trial data to build ground truth from. Inventing
ground truth against *real* trial records would have meant either
fabricating facts about real trials (unacceptable for a project whose
entire premise is "never fabricate clinical data") or spending
significant effort hand-verifying real facts with no way to confirm them
against a live source in this environment. A synthetic corpus — fake
drugs, fake conditions, but real (if simple) ClinicalTrials.gov/PubMed
API *shapes*, exercised through the exact same `normalize_trial`/
`normalize_publication` functions Phase 2 already wrote — was the only
way to get ground truth this report's author could point to directly
and verify was not fabricated. `data/evaluation/fixtures_ctgov.json`'s
own `_fixture_note` documents this rationale for anyone who finds the
dataset later without this file.

**The `app/api/deps.py` refactor was necessary, not optional, for the
"end-to-end test" deliverable.** Phases 3–4 called
`get_settings()`/`get_embedding_provider(settings)`/
`get_claude_client(settings)` as plain function calls inside route
handlers. That's simpler code, but it gives `app.dependency_overrides`
nothing to attach to — the standard, idiomatic FastAPI way to substitute
a test double. Without this refactor, testing `/ask`/`/compare`
end-to-end would have required monkeypatching the imported names in
`app.api.qa`, exactly the kind of import-order-sensitive, fragile
test-only workaround this project has avoided everywhere else (see
`app/generation/answer.py`'s docstring on why `retrieve`/`claude_client`
are passed as parameters in the first place). The refactor is
deliberately minimal: three new functions in a new file, three call
sites changed from a direct call to a `Depends(...)` default, and zero
changes to what those functions actually do. Production behavior with no
override installed is unchanged.

**Two sandbox-verification scripts under `scripts/sandbox_verification/`
are not part of the shipped application — they're one-off proof that the
evaluation math and the ingestion/embedding/fusion code actually work
against a real Postgres, written because `sqlalchemy`/`psycopg` aren't
installed here and the real `app/retrieval/*.py` modules couldn't be
imported as-is.** They call the real `app.ingestion.normalize`,
`app.retrieval.embeddings.HashingEmbeddingProvider`,
`app.retrieval.fusion.reciprocal_rank_fusion`, and
`app.evaluation.metrics` functions directly, and hand-write the SQL
those retrieval modules would otherwise issue via SQLAlchemy — kept
byte-for-byte identical to `app/retrieval/fulltext.py`'s query. They are
retained in the repo (rather than deleted after use) specifically so the
Phase 6 evaluation report's real numbers are reproducible and auditable,
not just claimed. `docs/evaluation-report.md` labels their "hybrid" run
explicitly as "hybrid-**equivalent**" throughout, since it computes
cosine similarity in Python rather than through the real pgvector SQL
path, and never blurs that distinction.

**The fulltext-only real result (Recall@5 = MRR = 0.0000) is reported as
a genuine finding, not hidden or reframed to look better.** It would
have been easy to only run the hybrid-equivalent check and omit the
discouraging fulltext-only number, or to quietly rephrase the evaluation
questions to work around `plainto_tsquery`'s AND semantics. Neither
happened: both real results are in the report, the root cause was
diagnosed with a direct, documented test (not guessed at), and the
finding is cross-referenced into `docs/known-limitations.md` because it
is genuinely useful information about how this system behaves, not
just an artifact of the evaluation setup.

## What was actually built

- `data/evaluation/fixtures_ctgov.json`, `fixtures_pubmed.xml` — the
  synthetic corpus (5 trials, 3 publications).
- `data/evaluation/questions.json` — 20 questions (15 answerable, 5
  abstention traps), each with a `ground_truth_basis` explaining exactly
  which source document supports its answer.
- `backend/app/evaluation/metrics.py` — `recall_at_k`,
  `reciprocal_rank`, `mean_recall_at_k`, `mean_reciprocal_rank`,
  `citation_correctness`, `citation_completeness`, `abstention_accuracy`,
  `abstention_confusion_counts`. Pure, dependency-free, fully tested.
- `backend/app/evaluation/paths.py` — shared fixture-file path
  constants, deliberately dependency-free (see its docstring) so
  dataset-validation tests never need to import `sqlalchemy` just to
  find a file.
- `backend/app/evaluation/dataset.py` — `EvalQuestion`, `load_questions`,
  `validate_questions` (referential-integrity checks against the real
  corpus, not just shape checks).
- `backend/app/evaluation/seed_fixtures.py` — seeds the fixture corpus
  using the real Phase 2 `normalize_trial`/`normalize_publication`/
  `upsert_trial`/`upsert_publication` functions.
- `backend/app/evaluation/report.py` — `QuestionResult`,
  `EvaluationReport`, and a Markdown renderer.
- `backend/app/evaluation/run_eval.py` — the CLI orchestrator, including
  `ScriptedFakeClaudeClient` for harness self-testing.
- `backend/app/api/deps.py` — the three `Depends()`-wrapped factories.
- `backend/app/api/qa.py`, `retrieval.py` — updated to take their
  dependencies via `Depends(...)` instead of calling the factories
  directly.
- `tests/test_evaluation_metrics.py`, `test_evaluation_dataset.py`,
  `test_end_to_end.py` — see `docs/evaluation-report.md` for exactly
  which of these were executed here versus written-and-reasoned-through.
- `tests/conftest.py` — the autouse `_reset_dependency_overrides`
  fixture now also resets the two new dependency overrides.
- `docs/architecture.md` and the README's summary diagram — both
  Mermaid diagrams were rendered with `mmdc` in this sandbox (pointed at
  the pre-installed Playwright Chromium via `PUPPETEER_EXECUTABLE_PATH`,
  since `mmdc`'s own bundled Chrome isn't installed here) to confirm
  they're syntactically valid and actually lay out as a graph.
- `docs/evaluation-report.md`, `docs/known-limitations.md`,
  `docs/deployment.md` — see each for its own contents.
- `README.md` — full portfolio-quality rewrite.
- `scripts/sandbox_verification/` — the two one-off verification
  scripts and their real output, described above.

## What was actually verified, and how

See `docs/evaluation-report.md`'s "What actually ran" section for the
full, detailed breakdown (33/33 metric-test methods, 13/13 dataset-test
methods, two real Postgres-backed retrieval checks — the release-audit
report, `docs/release-report.md`, has the precise assert-statement
counts and notes a miscount this phase's notes originally had). In
addition to that:

- **Every file this phase touched or added, across the whole repo, was
  syntax-checked for real**: `python3 -m py_compile` over every `.py`
  file under `backend/app/` and `tests/` (not just this phase's new
  files) completed with zero errors.
- `app/api/qa.py` and `app/api/retrieval.py` were re-read in full after
  editing and checked by hand against the pre-refactor versions to
  confirm no call site was missed and no behavior changed beyond the
  dependency-injection seam itself.

Not verified in this environment (blocked by the same package-registry
and API-key gaps as every prior phase, not a known defect):

- The full `pytest` suite (this phase's new tests and every prior
  phase's), since `pytest`/`fastapi`/`sqlalchemy` aren't installed here.
- `tests/test_end_to_end.py` actually running and passing.
- `app/evaluation/run_eval.py` actually running, in either
  `--claude-client` mode.
- Real hybrid/dense Recall@5/MRR through the real pgvector SQL path.
- Real citation correctness/completeness/abstention accuracy against an
  actual Claude response.
- The Mermaid diagram's *rendered appearance* beyond "it doesn't error"
  — `mmdc` produced a valid SVG, but no one has looked at it and judged
  whether the layout reads well.
- A real Docker build/`docker compose up` of the full stack (Docker
  itself isn't available to this sandbox as a runtime, only reasoned
  about from the existing `docker-compose.yml`/Dockerfiles).

## Commands to finish verification yourself

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db   # Postgres 16 + pgvector

cd ..
PYTHONPATH=backend pytest                              # full suite
PYTHONPATH=backend python -m app.evaluation.run_eval \
    --claude-client fake-self-test                     # harness self-test, no API key needed
PYTHONPATH=backend python -m app.evaluation.run_eval \
    --claude-client real --output docs/evaluation-report-real.md   # needs ANTHROPIC_API_KEY

make up                                                 # full Docker stack, see docs/deployment.md
```

If `pytest` surfaces a failure the sandbox verification here couldn't
have caught — a real SQLAlchemy/FastAPI integration issue, a real
pgvector query error, a real Claude response that doesn't validate the
way the scripted fake did — that's the real signal to act on, exactly as
every prior phase's notes have said about their own unexecuted tests.
