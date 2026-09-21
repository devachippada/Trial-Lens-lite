"""Seed the Phase 6 synthetic fixture corpus into a database.

Deliberately reuses the exact same functions Phase 2's real ingestion
CLIs use — ``app.ingestion.normalize.normalize_trial``/
``normalize_publication`` and ``app.ingestion.ingest_clinicaltrials
.upsert_trial``/``app.ingestion.ingest_pubmed.upsert_publication`` — so
this is not a reimplementation of ingestion, just those same functions
pointed at ``data/evaluation/fixtures_ctgov.json``/``fixtures_pubmed.xml``
instead of a live network call to ClinicalTrials.gov/PubMed. That
mirrors the pattern Phase 2's own test fixtures already used
(``tests/fixtures/ctgov_study_sample.json``/``pubmed_efetch_sample.xml``)
and means a bug fixed in real ingestion is automatically exercised here
too, rather than needing a parallel fix.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy.orm import Session

from app.evaluation.paths import DEFAULT_CTGOV_FIXTURES, DEFAULT_PUBMED_FIXTURES
from app.ingestion.ingest_clinicaltrials import upsert_trial
from app.ingestion.ingest_pubmed import upsert_publication
from app.ingestion.normalize import normalize_publication, normalize_trial


def seed_trials(session: Session, path: Path = DEFAULT_CTGOV_FIXTURES) -> list[str]:
    """Upsert every trial in the fixture file. Returns the nct_ids upserted."""

    data = json.loads(Path(path).read_text())
    nct_ids = []
    for raw_study in data["studies"]:
        normalized = normalize_trial(raw_study)
        upsert_trial(session, normalized)
        nct_ids.append(normalized.nct_id)
    session.flush()
    return nct_ids


def seed_publications(session: Session, path: Path = DEFAULT_PUBMED_FIXTURES) -> list[str]:
    """Upsert every publication in the fixture file. Returns the pmids upserted."""

    raw_xml = Path(path).read_text()
    root = ET.fromstring(raw_xml)
    pmids = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        article_xml = ET.tostring(article, encoding="unicode")
        normalized = normalize_publication(pmid, article_xml, article)
        upsert_publication(session, normalized)
        pmids.append(normalized.pmid)
    session.flush()
    return pmids


def seed_all(
    session: Session,
    ctgov_path: Path = DEFAULT_CTGOV_FIXTURES,
    pubmed_path: Path = DEFAULT_PUBMED_FIXTURES,
) -> dict[str, list[str]]:
    """Seed both fixture files. Does not commit — callers control the
    transaction (a test typically rolls it back; ``run_eval.py`` commits
    it so the corpus is inspectable afterward).
    """

    nct_ids = seed_trials(session, ctgov_path)
    pmids = seed_publications(session, pubmed_path)
    return {"nct_ids": nct_ids, "pmids": pmids}
