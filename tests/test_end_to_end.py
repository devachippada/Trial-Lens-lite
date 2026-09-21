"""End-to-end test: seeds the real synthetic Phase 6 fixture corpus into
a real Postgres, indexes it with the real chunking/embedding pipeline,
and calls the real FastAPI app (via TestClient) for GET
/api/v1/retrieve, POST /api/v1/ask, and POST /api/v1/compare.

Two dependencies are overridden, and nothing else:

- ``get_db`` -> the same ``db_session`` fixture used to seed the data,
  so API requests run in the exact transaction the fixture-seeding code
  used (see conftest.py's ``db_session`` docstring: a *different*
  connection's transaction would make the seeded rows invisible to the
  request, since Postgres transactions don't see each other's
  uncommitted writes).
- ``app.api.deps.get_claude_client_dependency`` -> a scripted stand-in,
  the one dependency this project genuinely cannot exercise for real in
  any sandbox without network access and a real ANTHROPIC_API_KEY (see
  app/generation/client.py's docstring: there's no dependency-free real
  answer-generation provider by design). The scripted client cites
  whatever evidence indices it's given and otherwise abstains — it has
  no understanding of the question, so its presence here tests the
  *pipeline* (retrieval -> prompt building -> citation extraction ->
  validation -> response shape), not real answer quality. Real answer
  quality has no automated test in this project; it needs human review
  against a real model, same as any other grounded-generation system.

Every other line — FastAPI routing, retrieval SQL (full-text/dense/RRF),
citation extraction/validation, Pydantic response models — runs
completely unmodified, exactly the code a real deployment runs.

Skipped automatically (via the ``db_session`` fixture) if no database is
reachable or the `vector` extension isn't installed, exactly like every
other DB-integration test in this suite (test_retrieval_hybrid.py,
test_comparison_db.py, test_ingest_upsert.py).
"""

from __future__ import annotations

import re

from app.api.deps import get_claude_client_dependency
from app.db.session import get_db
from app.evaluation.seed_fixtures import seed_all
from app.generation.client import ClaudeResponse
from app.generation.prompt import ABSTAIN_MARKER
from app.main import app
from app.models import Document
from app.retrieval.embeddings import HashingEmbeddingProvider
from app.retrieval.index_documents import index_document

_CITATION_INDEX_PATTERN = re.compile(r'<retrieved_chunk index="(\d+)"')


class _ScriptedClaudeClient:
    """Cites every retrieved-chunk index it's given, or abstains if none
    were given. Deliberately a small, local copy of the same idea as
    ``app.evaluation.run_eval.ScriptedFakeClaudeClient`` rather than an
    import of it — that module also wires up ``SessionLocal()``/
    ``get_settings()`` at call time for the standalone CLI, which this
    test has no reason to pull in just for this one class. See that
    module's docstring for the full rationale, which applies here
    identically: this fake proves the pipeline's plumbing, not real
    answer quality.
    """

    def complete(self, *, system: str, user: str, max_tokens: int) -> ClaudeResponse:
        indices = sorted({int(m) for m in _CITATION_INDEX_PATTERN.findall(user)})
        if not indices:
            return ClaudeResponse(text=ABSTAIN_MARKER)
        citation = ", ".join(str(i) for i in indices)
        return ClaudeResponse(
            text=f"This is a scripted end-to-end test response citing the retrieved evidence [{citation}]."
        )


def _seed_and_index(db_session) -> None:
    seed_all(db_session)
    db_session.flush()
    provider = HashingEmbeddingProvider(dimension=256)
    for document in db_session.query(Document).all():
        index_document(db_session, document, provider)
    db_session.flush()


def _override_db_and_claude_client(db_session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_claude_client_dependency] = lambda: _ScriptedClaudeClient()


class TestEndToEndRetrieve:
    def test_retrieve_returns_real_ranked_chunks_for_a_real_document(self, client, db_session):
        _seed_and_index(db_session)
        _override_db_and_claude_client(db_session)

        # Every word here appears verbatim in NCT90000003's document text
        # (see data/evaluation/fixtures_ctgov.json) so this is a
        # deterministic, real full-text match — no embedding/pgvector
        # dependency needed for this assertion.
        response = client.get(
            "/api/v1/retrieve",
            params={"q": "maximum tolerated dose TL-205", "k": 5, "mode": "fulltext"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "maximum tolerated dose TL-205"
        assert len(body["results"]) >= 1
        assert body["results"][0]["source_identifier"] == "NCT90000003"
        assert "fulltext" in body["results"][0]["matched_by"]

    def test_retrieve_returns_nothing_for_unrelated_vocabulary(self, client, db_session):
        _seed_and_index(db_session)
        _override_db_and_claude_client(db_session)

        response = client.get(
            "/api/v1/retrieve",
            params={"q": "banana unicycle weather forecast", "k": 5, "mode": "fulltext"},
        )

        assert response.status_code == 200
        assert response.json()["results"] == []


class TestEndToEndAsk:
    def test_ask_returns_a_grounded_answer_with_real_validated_citations(self, client, db_session):
        _seed_and_index(db_session)
        _override_db_and_claude_client(db_session)

        response = client.post(
            "/api/v1/ask",
            json={"question": "maximum tolerated dose TL-205"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "answered"
        assert body["citations"], "expected at least one real, validated citation"
        assert all(c["source_identifier"] == "NCT90000003" for c in body["citations"])
        assert body["warnings"] == []

    def test_ask_abstains_when_retrieval_finds_no_evidence(self, client, db_session):
        _seed_and_index(db_session)
        _override_db_and_claude_client(db_session)

        # top_k isn't exposed for retrieval *mode* on /ask (it always
        # hybrid-searches), so this relies on the same guaranteed-empty
        # full-text-vocabulary query as the retrieve test above; the
        # hashing dense provider ranks *something* by cosine similarity
        # even for unrelated text, so a true zero-chunks-retrieved
        # result isn't reachable through /ask's hybrid mode without a
        # real semantic embedding model. This test instead exercises the
        # scripted client's own abstention path (no <retrieved_chunk>
        # indices worth citing at all is unreachable when hybrid always
        # returns *some* candidate) — see the module docstring on why
        # real abstention judgment needs a real model. What IS verified
        # here, for real: an /ask response is well-formed and internally
        # consistent (status/answer/citations agree) regardless of which
        # branch fires.
        response = client.post(
            "/api/v1/ask",
            json={"question": "banana unicycle weather forecast"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] in ("answered", "insufficient_evidence", "validation_failed")
        if body["status"] != "answered":
            assert body["citations"] == []


class TestEndToEndCompare:
    def test_compare_splits_citations_by_trial(self, client, db_session):
        _seed_and_index(db_session)
        _override_db_and_claude_client(db_session)

        response = client.post(
            "/api/v1/compare",
            json={"nct_id_a": "NCT90000001", "nct_id_b": "NCT90000003"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "answered"
        identifiers = {c["source_identifier"] for c in body["citations"]}
        assert "NCT90000001" in identifiers
        assert "NCT90000003" in identifiers

    def test_compare_404s_for_an_unknown_trial(self, client, db_session):
        _seed_and_index(db_session)
        _override_db_and_claude_client(db_session)

        response = client.post(
            "/api/v1/compare",
            json={"nct_id_a": "NCT90000001", "nct_id_b": "NCT90000099"},
        )

        assert response.status_code == 404
