"""Integration tests for full-text, dense, and hybrid (RRF) retrieval
against a real Postgres — skipped automatically if no database is
reachable, or if the `vector` extension isn't installed, per the
`db_session` fixture in conftest.py.

These exercise the actual SQL in app/retrieval/fulltext.py and
app/retrieval/dense.py (ts_rank / pgvector `<=>`), not a mock, plus the
orchestration in app/retrieval/hybrid.py that fuses them with RRF.
"""

import pytest

from app.ingestion.normalize import sha256_hex
from app.models import Chunk, Document, Trial
from app.retrieval import dense as dense_module
from app.retrieval import fulltext as fulltext_module
from app.retrieval import hybrid
from app.retrieval.embeddings import HashingEmbeddingProvider


@pytest.fixture
def provider() -> HashingEmbeddingProvider:
    return HashingEmbeddingProvider(dimension=64)


@pytest.fixture
def document(db_session) -> Document:
    """One trial + one document, ready to hang chunks off of."""

    trial = Trial(
        nct_id="NCT00000001",
        source_url="https://clinicaltrials.gov/study/NCT00000001",
        brief_title="A test trial",
        overall_status="COMPLETED",
        content_hash=sha256_hex("trial-NCT00000001"),
        raw_data={"fixture": True},
    )
    db_session.add(trial)
    db_session.flush()

    doc_text = "placeholder"
    doc = Document(
        source_type="trial",
        trial_id=trial.id,
        source_identifier=trial.nct_id,
        source_url=trial.source_url,
        title=trial.brief_title,
        text=doc_text,
        content_hash=sha256_hex(doc_text),
    )
    db_session.add(doc)
    db_session.flush()
    return doc


def _add_chunk(db_session, document, index, text, embedding=None):
    chunk = Chunk(
        document_id=document.id,
        chunk_index=index,
        text=text,
        char_start=0,
        char_end=len(text),
        content_hash=sha256_hex(text),
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.flush()
    return chunk


class TestFulltextSearch:
    def test_finds_chunk_containing_the_query_terms(self, db_session, document):
        target = _add_chunk(
            db_session, document, 0, "Overall survival was significantly improved in the treatment arm."
        )
        _add_chunk(db_session, document, 1, "Adverse events were mild and self-limiting in most patients.")

        hits = fulltext_module.fulltext_search(db_session, "overall survival", limit=10)

        assert len(hits) == 1
        assert hits[0].chunk_id == target.id
        assert hits[0].score > 0

    def test_no_match_returns_empty_list(self, db_session, document):
        _add_chunk(db_session, document, 0, "Overall survival was significantly improved.")

        hits = fulltext_module.fulltext_search(db_session, "xenomorph teleportation", limit=10)

        assert hits == []

    def test_respects_limit(self, db_session, document):
        for i in range(5):
            _add_chunk(db_session, document, i, f"progression free survival result number {i}")

        hits = fulltext_module.fulltext_search(db_session, "progression free survival", limit=2)

        assert len(hits) == 2


class TestDenseSearch:
    def test_finds_the_most_similar_chunk(self, db_session, document, provider):
        near_text = "Grade 3 adverse events occurred in twelve percent of patients."
        far_text = "The sky was clear and the launch proceeded on schedule."

        near_chunk = _add_chunk(
            db_session, document, 0, near_text, embedding=provider.embed([near_text])[0]
        )
        _add_chunk(db_session, document, 1, far_text, embedding=provider.embed([far_text])[0])

        [query_embedding] = provider.embed([near_text])
        hits = dense_module.dense_search(db_session, query_embedding, limit=10)

        assert hits[0].chunk_id == near_chunk.id
        # Identical text against itself is cosine-identical: score ~ 1.0.
        assert hits[0].score == pytest.approx(1.0, abs=1e-6)

    def test_excludes_chunks_with_no_embedding(self, db_session, document, provider):
        embedded_text = "Median follow-up was eighteen months."
        embedded = _add_chunk(
            db_session, document, 0, embedded_text, embedding=provider.embed([embedded_text])[0]
        )
        _add_chunk(db_session, document, 1, "This chunk was never embedded.", embedding=None)

        [query_embedding] = provider.embed([embedded_text])
        hits = dense_module.dense_search(db_session, query_embedding, limit=10)

        assert [h.chunk_id for h in hits] == [embedded.id]

    def test_respects_limit(self, db_session, document, provider):
        for i in range(5):
            text = f"safety data point number {i}"
            _add_chunk(db_session, document, i, text, embedding=provider.embed([text])[0])

        [query_embedding] = provider.embed(["safety data point"])
        hits = dense_module.dense_search(db_session, query_embedding, limit=2)

        assert len(hits) == 2


class TestHybridSearch:
    def test_empty_query_returns_no_results(self, db_session, document, provider):
        _add_chunk(db_session, document, 0, "some text", embedding=provider.embed(["some text"])[0])

        assert hybrid.search(db_session, "", provider) == []
        assert hybrid.search(db_session, "   ", provider) == []

    def test_hybrid_mode_returns_results_findable_by_either_retriever(self, db_session, document, provider):
        keyword_text = "Pembrolizumab demonstrated a statistically significant overall survival benefit."
        other_text = "Unrelated safety monitoring notes for a different arm of the study."

        keyword_chunk = _add_chunk(
            db_session, document, 0, keyword_text, embedding=provider.embed([keyword_text])[0]
        )
        _add_chunk(db_session, document, 1, other_text, embedding=provider.embed([other_text])[0])

        results = hybrid.search(db_session, "pembrolizumab overall survival", provider, mode="hybrid")

        assert len(results) >= 1
        top = results[0]
        assert top.chunk_id == keyword_chunk.id
        assert top.document_id == document.id
        assert top.source_type == "trial"
        assert top.source_identifier == "NCT00000001"
        assert top.excerpt == keyword_text
        assert "fulltext" in top.matched_by

    def test_fulltext_only_mode_does_not_call_the_embedding_provider(self, db_session, document):
        _add_chunk(db_session, document, 0, "Overall survival endpoint met.")

        class ExplodingProvider:
            dimension = 64

            def embed(self, texts):
                raise AssertionError("dense embedding should not run in fulltext mode")

        results = hybrid.search(db_session, "overall survival", ExplodingProvider(), mode="fulltext")

        assert len(results) == 1
        assert results[0].matched_by == ["fulltext"]

    def test_dense_only_mode_skips_fulltext_ranking(self, db_session, document, provider):
        text = "Quality of life scores improved over the treatment period."
        chunk = _add_chunk(db_session, document, 0, text, embedding=provider.embed([text])[0])

        results = hybrid.search(db_session, text, provider, mode="dense")

        assert len(results) == 1
        assert results[0].chunk_id == chunk.id
        assert results[0].matched_by == ["dense"]

    def test_top_k_limits_result_count(self, db_session, document, provider):
        for i in range(5):
            text = f"endpoint measurement number {i} for the study cohort"
            _add_chunk(db_session, document, i, text, embedding=provider.embed([text])[0])

        results = hybrid.search(db_session, "endpoint measurement", provider, mode="hybrid", top_k=2)

        assert len(results) <= 2
