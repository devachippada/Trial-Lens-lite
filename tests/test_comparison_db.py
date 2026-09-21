"""DB integration test for assemble_trial_chunks (app/generation/comparison.py)
— skipped automatically if no database is reachable, or the `vector`
extension isn't installed, per the `db_session` fixture in conftest.py.

Everything else in app/generation/comparison.py is pure and is covered
without a database in tests/test_comparison.py.
"""

from app.generation.comparison import assemble_trial_chunks
from app.ingestion.normalize import sha256_hex
from app.models import Chunk, Document, Trial


def _make_trial_with_chunks(db_session, nct_id, chunk_texts):
    trial = Trial(
        nct_id=nct_id,
        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
        brief_title="A test trial",
        overall_status="COMPLETED",
        content_hash=sha256_hex(f"trial-{nct_id}"),
        raw_data={"fixture": True},
    )
    db_session.add(trial)
    db_session.flush()

    doc_text = "placeholder"
    document = Document(
        source_type="trial",
        trial_id=trial.id,
        source_identifier=nct_id,
        source_url=trial.source_url,
        title=trial.brief_title,
        text=doc_text,
        content_hash=sha256_hex(doc_text),
    )
    db_session.add(document)
    db_session.flush()

    for index, text in enumerate(chunk_texts):
        db_session.add(
            Chunk(
                document_id=document.id,
                chunk_index=index,
                text=text,
                char_start=0,
                char_end=len(text),
                content_hash=sha256_hex(text),
            )
        )
    db_session.flush()
    return trial


class TestAssembleTrialChunks:
    def test_returns_chunks_in_document_order(self, db_session):
        _make_trial_with_chunks(
            db_session, "NCT00000010", ["first chunk", "second chunk", "third chunk"]
        )

        chunks = assemble_trial_chunks(db_session, "NCT00000010", limit=10)

        assert [c.excerpt for c in chunks] == ["first chunk", "second chunk", "third chunk"]

    def test_respects_the_limit(self, db_session):
        _make_trial_with_chunks(db_session, "NCT00000011", [f"chunk {i}" for i in range(5)])

        chunks = assemble_trial_chunks(db_session, "NCT00000011", limit=2)

        assert len(chunks) == 2

    def test_returns_none_for_an_unknown_trial(self, db_session):
        assert assemble_trial_chunks(db_session, "NCT99999999", limit=10) is None

    def test_returns_empty_list_for_a_trial_with_no_chunks_yet(self, db_session):
        _make_trial_with_chunks(db_session, "NCT00000012", [])

        assert assemble_trial_chunks(db_session, "NCT00000012", limit=10) == []
