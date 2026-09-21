"""Tests for app.ingestion.normalize using the fixture files.

These exercise only the pure parsing/normalization functions — no
network, no database — against the synthetic fixtures in
tests/fixtures/.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.ingestion.normalize import (
    canonical_json,
    extract_nct_ids,
    normalize_publication,
    normalize_trial,
    parse_ctgov_date,
    sha256_hex,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ctgov_raw() -> dict:
    return json.loads((FIXTURES_DIR / "ctgov_study_sample.json").read_text())


@pytest.fixture
def pubmed_article_xml() -> tuple[str, str, ET.Element]:
    raw_xml = (FIXTURES_DIR / "pubmed_efetch_sample.xml").read_text()
    root = ET.fromstring(raw_xml)
    article = root.find(".//PubmedArticle")
    assert article is not None, "fixture file must contain a <PubmedArticle> element"
    article_xml = ET.tostring(article, encoding="unicode")
    pmid = article.findtext(".//PMID")
    assert pmid is not None, "fixture <PubmedArticle> must contain a <PMID> element"
    return pmid, article_xml, article


class TestNormalizeTrial:
    def test_extracts_core_fields(self, ctgov_raw):
        trial = normalize_trial(ctgov_raw)

        assert trial.nct_id == "NCT99999999"
        assert trial.source_url == "https://clinicaltrials.gov/study/NCT99999999"
        assert trial.brief_title.startswith("A Study of Example Drug")
        assert trial.overall_status == "COMPLETED"
        assert trial.phase == "PHASE3"
        assert trial.study_type == "INTERVENTIONAL"
        assert trial.conditions == ["Example Condition", "Example Condition Stage III"]
        assert trial.intervention_names == ["Example Drug", "Placebo"]
        assert trial.sponsor_name == "Example Sponsor, Inc."
        assert trial.enrollment_count == 412

    def test_parses_dates_including_partial_ones(self, ctgov_raw):
        trial = normalize_trial(ctgov_raw)

        assert trial.start_date.isoformat() == "2019-03-01"  # "2019-03" -> day defaults to 1
        assert trial.primary_completion_date.isoformat() == "2021-06-15"
        assert trial.last_update_posted_date.isoformat() == "2022-01-10"

    def test_preserves_endpoints(self, ctgov_raw):
        trial = normalize_trial(ctgov_raw)

        assert trial.primary_outcomes[0]["measure"] == "Overall Response Rate"
        assert trial.secondary_outcomes[0]["measure"] == "Overall Survival"

    def test_document_text_combines_summary_and_description(self, ctgov_raw):
        trial = normalize_trial(ctgov_raw)

        assert "evaluates whether Example Drug" in trial.document_text
        assert "randomized 1:1" in trial.document_text

    def test_content_hash_is_deterministic(self, ctgov_raw):
        trial_a = normalize_trial(ctgov_raw)
        trial_b = normalize_trial(json.loads(json.dumps(ctgov_raw)))  # deep-copied

        assert trial_a.content_hash == trial_b.content_hash
        assert trial_a.content_hash == sha256_hex(canonical_json(ctgov_raw))

    def test_content_hash_changes_when_data_changes(self, ctgov_raw):
        trial_a = normalize_trial(ctgov_raw)

        changed = json.loads(json.dumps(ctgov_raw))
        changed["protocolSection"]["statusModule"]["overallStatus"] = "RECRUITING"
        trial_b = normalize_trial(changed)

        assert trial_a.content_hash != trial_b.content_hash

    def test_missing_optional_fields_do_not_raise(self):
        minimal = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Minimal Study"},
                "statusModule": {"overallStatus": "UNKNOWN"},
            }
        }

        trial = normalize_trial(minimal)

        assert trial.nct_id == "NCT00000001"
        assert trial.conditions == []
        assert trial.intervention_names == []
        assert trial.start_date is None
        assert trial.document_text == ""


class TestNormalizeDate:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ({"date": "2020-05-04"}, "2020-05-04"),
            ({"date": "2020-05"}, "2020-05-01"),
            ({"date": "2020"}, "2020-01-01"),
            ("2020-05-04", "2020-05-04"),
            (None, None),
            ({}, None),
            ({"date": ""}, None),
        ],
    )
    def test_parse_ctgov_date(self, value, expected):
        result = parse_ctgov_date(value)
        assert (result.isoformat() if result else None) == expected


class TestNormalizePublication:
    def test_extracts_core_fields(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        assert pub.pmid == "99999999"
        assert pub.source_url == "https://pubmed.ncbi.nlm.nih.gov/99999999/"
        assert "randomized trial" in pub.title
        assert pub.journal == "Journal of Example Medicine"
        assert pub.doi == "10.9999/example.2022.001"

    def test_publication_date_parsed(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        assert pub.publication_date.isoformat() == "2022-03-15"
        assert pub.publication_year == 2022

    def test_abstract_joins_labeled_sections(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        assert "BACKGROUND:" in pub.abstract
        assert "METHODS:" in pub.abstract
        assert "RESULTS:" in pub.abstract
        assert pub.document_text == pub.abstract

    def test_authors_parsed(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        assert pub.authors == ["Smith JA", "Doe RB"]

    def test_mesh_terms_parsed(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        assert "Example Condition" in pub.mesh_terms
        assert "Randomized Controlled Trial" in pub.mesh_terms

    def test_linked_nct_ids_from_databank_and_abstract(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        # Same ID appears in both <DataBank> and the abstract text; it
        # should be de-duplicated to a single entry.
        assert pub.linked_nct_ids == ["NCT99999999"]

    def test_content_hash_is_raw_xml_hash(self, pubmed_article_xml):
        pmid, article_xml, article = pubmed_article_xml
        pub = normalize_publication(pmid, article_xml, article)

        assert pub.content_hash == sha256_hex(article_xml)


class TestExtractNctIds:
    def test_finds_multiple_distinct_ids(self):
        text = "See NCT01234567 and also NCT07654321 for related work."
        assert extract_nct_ids(text) == ["NCT01234567", "NCT07654321"]

    def test_deduplicates_preserving_order(self):
        text = "NCT01234567 ... later again NCT01234567"
        assert extract_nct_ids(text) == ["NCT01234567"]

    def test_empty_or_none_text(self):
        assert extract_nct_ids(None) == []
        assert extract_nct_ids("") == []
        assert extract_nct_ids("no ids here") == []
