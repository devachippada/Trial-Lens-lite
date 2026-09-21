"""Integration tests for the upsert (new/unchanged/updated) logic in the
ingestion scripts, against a real Postgres — skipped automatically if
DATABASE_URL isn't reachable (see conftest.py's `db_session` fixture).

These are the tests that actually prove duplicate detection works
end-to-end: re-running ingestion against unchanged upstream data must
not create a second row, and a changed upstream record must update the
existing row rather than duplicate it.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.ingestion.dedup import DedupAction
from app.ingestion.ingest_clinicaltrials import upsert_trial
from app.ingestion.ingest_pubmed import upsert_publication
from app.ingestion.normalize import normalize_publication, normalize_trial
from app.models import Document, Publication, Trial

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ctgov_raw() -> dict:
    return json.loads((FIXTURES_DIR / "ctgov_study_sample.json").read_text())


@pytest.fixture
def pubmed_article():
    raw_xml = (FIXTURES_DIR / "pubmed_efetch_sample.xml").read_text()
    root = ET.fromstring(raw_xml)
    article = root.find(".//PubmedArticle")
    article_xml = ET.tostring(article, encoding="unicode")
    pmid = article.findtext(".//PMID")
    return pmid, article_xml, article


class TestUpsertTrial:
    def test_first_ingest_creates_trial_and_document(self, db_session, ctgov_raw):
        normalized = normalize_trial(ctgov_raw)

        action = upsert_trial(db_session, normalized)
        db_session.flush()

        assert action == DedupAction.NEW
        trial = db_session.query(Trial).filter_by(nct_id="NCT99999999").one()
        document = db_session.query(Document).filter_by(trial_id=trial.id).one()
        assert document.source_type == "trial"
        assert document.text == normalized.document_text

    def test_reingesting_unchanged_data_does_not_duplicate(self, db_session, ctgov_raw):
        normalized = normalize_trial(ctgov_raw)
        upsert_trial(db_session, normalized)
        db_session.flush()

        action = upsert_trial(db_session, normalize_trial(ctgov_raw))
        db_session.flush()

        assert action == DedupAction.UNCHANGED
        assert db_session.query(Trial).filter_by(nct_id="NCT99999999").count() == 1

    def test_reingesting_changed_data_updates_in_place(self, db_session, ctgov_raw):
        upsert_trial(db_session, normalize_trial(ctgov_raw))
        db_session.flush()

        changed = json.loads(json.dumps(ctgov_raw))
        changed["protocolSection"]["statusModule"]["overallStatus"] = "TERMINATED"
        action = upsert_trial(db_session, normalize_trial(changed))
        db_session.flush()

        assert action == DedupAction.UPDATED
        rows = db_session.query(Trial).filter_by(nct_id="NCT99999999").all()
        assert len(rows) == 1
        assert rows[0].overall_status == "TERMINATED"


class TestUpsertPublication:
    def test_first_ingest_creates_publication_and_document(self, db_session, pubmed_article):
        pmid, article_xml, article = pubmed_article
        normalized = normalize_publication(pmid, article_xml, article)

        action = upsert_publication(db_session, normalized)
        db_session.flush()

        assert action == DedupAction.NEW
        publication = db_session.query(Publication).filter_by(pmid="99999999").one()
        document = db_session.query(Document).filter_by(publication_id=publication.id).one()
        assert document.source_type == "publication"

    def test_reingesting_unchanged_data_does_not_duplicate(self, db_session, pubmed_article):
        pmid, article_xml, article = pubmed_article
        upsert_publication(db_session, normalize_publication(pmid, article_xml, article))
        db_session.flush()

        action = upsert_publication(db_session, normalize_publication(pmid, article_xml, article))
        db_session.flush()

        assert action == DedupAction.UNCHANGED
        assert db_session.query(Publication).filter_by(pmid="99999999").count() == 1

    def test_links_to_existing_trial_by_nct_id(self, db_session, ctgov_raw, pubmed_article):
        # The trial must exist locally first for the link to resolve.
        upsert_trial(db_session, normalize_trial(ctgov_raw))
        db_session.flush()
        trial = db_session.query(Trial).filter_by(nct_id="NCT99999999").one()

        pmid, article_xml, article = pubmed_article
        upsert_publication(db_session, normalize_publication(pmid, article_xml, article))
        db_session.flush()

        publication = db_session.query(Publication).filter_by(pmid="99999999").one()
        assert publication.linked_trial_id == trial.id
