"""CLI: ingest a small curated set of articles from PubMed.

Usage:

    python -m app.ingestion.ingest_pubmed \\
        --term "pembrolizumab AND clinical trial[pt]" --limit 10

Requires a running Postgres reachable via DATABASE_URL (see
.env.example) and network access to eutils.ncbi.nlm.nih.gov. Safe to
re-run: unchanged records are skipped, changed ones are updated in
place, and a Document row is upserted 1:1 with each Publication.
"""

from __future__ import annotations

import argparse
import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.config import DEFAULTS
from app.ingestion.dedup import DedupAction, classify_by_source_id, find_hash_collisions
from app.ingestion.normalize import NormalizedPublication, normalize_publication, sha256_hex
from app.ingestion.pubmed_client import PubMedClient
from app.models import Document, Publication, Trial

logger = logging.getLogger(__name__)


def _resolve_linked_trial(session: Session, nct_ids: list[str]) -> int | None:
    """If exactly one of the publication's referenced NCT ids matches a
    trial we already have locally, return its id; otherwise None.

    Deliberately conservative: with zero or multiple matches we leave the
    link unset rather than guess, since a wrong link would misattribute
    a publication to the wrong registered trial.
    """

    if not nct_ids:
        return None
    matches = session.query(Trial.id).filter(Trial.nct_id.in_(nct_ids)).all()
    if len(matches) == 1:
        return matches[0][0]
    return None


def upsert_publication(session: Session, normalized: NormalizedPublication) -> DedupAction:
    existing = session.query(Publication).filter_by(pmid=normalized.pmid).one_or_none()
    result = classify_by_source_id(
        existing_id=existing.id if existing else None,
        existing_content_hash=existing.content_hash if existing else None,
        new_content_hash=normalized.content_hash,
    )

    if result.action == DedupAction.UNCHANGED:
        logger.info("publication %s unchanged, skipping", normalized.pmid)
        return result.action

    linked_trial_id = _resolve_linked_trial(session, normalized.linked_nct_ids)

    if result.action == DedupAction.NEW:
        publication = Publication(
            pmid=normalized.pmid,
            doi=normalized.doi,
            source_url=normalized.source_url,
            title=normalized.title,
            journal=normalized.journal,
            publication_date=normalized.publication_date,
            publication_year=normalized.publication_year,
            authors=normalized.authors,
            abstract=normalized.abstract,
            mesh_terms=normalized.mesh_terms,
            linked_nct_ids=normalized.linked_nct_ids,
            linked_trial_id=linked_trial_id,
            content_hash=normalized.content_hash,
            raw_xml=normalized.raw_xml,
        )
        session.add(publication)
        logger.info("publication %s new", normalized.pmid)
    else:  # UPDATED
        publication = existing
        publication.doi = normalized.doi
        publication.source_url = normalized.source_url
        publication.title = normalized.title
        publication.journal = normalized.journal
        publication.publication_date = normalized.publication_date
        publication.publication_year = normalized.publication_year
        publication.authors = normalized.authors
        publication.abstract = normalized.abstract
        publication.mesh_terms = normalized.mesh_terms
        publication.linked_nct_ids = normalized.linked_nct_ids
        publication.linked_trial_id = linked_trial_id
        publication.content_hash = normalized.content_hash
        publication.raw_xml = normalized.raw_xml
        logger.info("publication %s updated", normalized.pmid)

    session.flush()  # assigns publication.id for a NEW row

    doc_text = normalized.document_text
    doc_content_hash = sha256_hex(f"{normalized.pmid}:{doc_text}")

    document = session.query(Document).filter_by(publication_id=publication.id).one_or_none()
    if document is None:
        document = Document(
            source_type="publication",
            publication_id=publication.id,
            source_identifier=normalized.pmid,
            source_url=normalized.source_url,
            title=normalized.title,
            text=doc_text,
            content_hash=doc_content_hash,
        )
        session.add(document)
    elif document.content_hash != doc_content_hash:
        document.title = normalized.title
        document.text = doc_text
        document.content_hash = doc_content_hash

    return result.action


def run(term: str, limit: int) -> dict[str, int]:
    settings = get_settings()
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    hashes_by_id: dict[str, str] = {}

    with httpx.Client(timeout=30.0) as http_client, SessionLocal() as session:
        client = PubMedClient(
            http_client,
            base_url=settings.pubmed_base_url,
            api_key=settings.ncbi_api_key,
            contact_email=settings.ncbi_contact_email,
        )
        pmids = client.esearch(term, retmax=limit)
        for pmid, article_xml, article in client.fetch_articles(pmids):
            if not pmid:
                logger.warning("skipping article with no PMID")
                continue
            normalized = normalize_publication(pmid, article_xml, article)
            hashes_by_id[normalized.pmid] = normalized.content_hash
            action = upsert_publication(session, normalized)
            counts[action.value] += 1

        session.commit()

    collisions = find_hash_collisions(hashes_by_id)
    for content_hash, pmids_ in collisions.items():
        logger.warning(
            "content-hash collision across distinct publications %s (hash %s) — "
            "these are stored as separate records regardless",
            pmids_,
            content_hash[:12],
        )

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", default=DEFAULTS.pubmed_query_term)
    parser.add_argument("--limit", type=int, default=DEFAULTS.page_size)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    counts = run(term=args.term, limit=args.limit)
    print(
        f"PubMed ingestion complete: "
        f"{counts['new']} new, {counts['updated']} updated, {counts['unchanged']} unchanged"
    )


if __name__ == "__main__":
    main()
