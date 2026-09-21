"""CLI: ingest a small curated set of studies from ClinicalTrials.gov.

Usage:

    python -m app.ingestion.ingest_clinicaltrials \\
        --intervention pembrolizumab --status COMPLETED --limit 10

Requires a running Postgres reachable via DATABASE_URL (see
.env.example) and network access to clinicaltrials.gov. Safe to re-run:
unchanged records are skipped, changed ones are updated in place, and a
Document row is upserted 1:1 with each Trial.
"""

from __future__ import annotations

import argparse
import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.clinicaltrials_client import ClinicalTrialsClient
from app.ingestion.config import DEFAULTS
from app.ingestion.dedup import DedupAction, classify_by_source_id, find_hash_collisions
from app.ingestion.normalize import NormalizedTrial, normalize_trial
from app.models import Document, Trial

logger = logging.getLogger(__name__)


def upsert_trial(session: Session, normalized: NormalizedTrial) -> DedupAction:
    existing = session.query(Trial).filter_by(nct_id=normalized.nct_id).one_or_none()
    result = classify_by_source_id(
        existing_id=existing.id if existing else None,
        existing_content_hash=existing.content_hash if existing else None,
        new_content_hash=normalized.content_hash,
    )

    if result.action == DedupAction.UNCHANGED:
        logger.info("trial %s unchanged, skipping", normalized.nct_id)
        return result.action

    if result.action == DedupAction.NEW:
        trial = Trial(
            nct_id=normalized.nct_id,
            source_url=normalized.source_url,
            brief_title=normalized.brief_title,
            official_title=normalized.official_title,
            overall_status=normalized.overall_status,
            phase=normalized.phase,
            study_type=normalized.study_type,
            conditions=normalized.conditions,
            intervention_names=normalized.intervention_names,
            sponsor_name=normalized.sponsor_name,
            enrollment_count=normalized.enrollment_count,
            start_date=normalized.start_date,
            primary_completion_date=normalized.primary_completion_date,
            completion_date=normalized.completion_date,
            last_update_posted_date=normalized.last_update_posted_date,
            brief_summary=normalized.brief_summary,
            detailed_description=normalized.detailed_description,
            primary_outcomes=normalized.primary_outcomes,
            secondary_outcomes=normalized.secondary_outcomes,
            content_hash=normalized.content_hash,
            raw_data=normalized.raw_data,
        )
        session.add(trial)
        logger.info("trial %s new", normalized.nct_id)
    else:  # UPDATED
        trial = existing
        trial.source_url = normalized.source_url
        trial.brief_title = normalized.brief_title
        trial.official_title = normalized.official_title
        trial.overall_status = normalized.overall_status
        trial.phase = normalized.phase
        trial.study_type = normalized.study_type
        trial.conditions = normalized.conditions
        trial.intervention_names = normalized.intervention_names
        trial.sponsor_name = normalized.sponsor_name
        trial.enrollment_count = normalized.enrollment_count
        trial.start_date = normalized.start_date
        trial.primary_completion_date = normalized.primary_completion_date
        trial.completion_date = normalized.completion_date
        trial.last_update_posted_date = normalized.last_update_posted_date
        trial.brief_summary = normalized.brief_summary
        trial.detailed_description = normalized.detailed_description
        trial.primary_outcomes = normalized.primary_outcomes
        trial.secondary_outcomes = normalized.secondary_outcomes
        trial.content_hash = normalized.content_hash
        trial.raw_data = normalized.raw_data
        logger.info("trial %s updated", normalized.nct_id)

    session.flush()  # assigns trial.id for a NEW row

    doc_text = normalized.document_text
    doc_hash_source = f"{normalized.nct_id}:{doc_text}"
    from app.ingestion.normalize import sha256_hex  # local import avoids a cycle at module load

    document = session.query(Document).filter_by(trial_id=trial.id).one_or_none()
    doc_content_hash = sha256_hex(doc_hash_source)
    if document is None:
        document = Document(
            source_type="trial",
            trial_id=trial.id,
            source_identifier=normalized.nct_id,
            source_url=normalized.source_url,
            title=normalized.brief_title,
            text=doc_text,
            content_hash=doc_content_hash,
        )
        session.add(document)
    elif document.content_hash != doc_content_hash:
        document.title = normalized.brief_title
        document.text = doc_text
        document.content_hash = doc_content_hash

    return result.action


def run(intervention: str, status: str | None, limit: int) -> dict[str, int]:
    settings = get_settings()
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    hashes_by_id: dict[str, str] = {}

    with httpx.Client(timeout=30.0) as http_client, SessionLocal() as session:
        client = ClinicalTrialsClient(http_client, base_url=settings.ctgov_base_url)
        for raw_study in client.search_studies(
            intervention=intervention, status=status, page_size=DEFAULTS.page_size, max_results=limit
        ):
            normalized = normalize_trial(raw_study)
            if not normalized.nct_id:
                logger.warning("skipping study with no nctId: %r", raw_study)
                continue
            hashes_by_id[normalized.nct_id] = normalized.content_hash
            action = upsert_trial(session, normalized)
            counts[action.value] += 1

        session.commit()

    collisions = find_hash_collisions(hashes_by_id)
    for content_hash, nct_ids in collisions.items():
        logger.warning(
            "content-hash collision across distinct trials %s (hash %s) — "
            "these are stored as separate records regardless",
            nct_ids,
            content_hash[:12],
        )

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervention", default=DEFAULTS.ctgov_query_intervention)
    parser.add_argument("--status", default=DEFAULTS.ctgov_query_status)
    parser.add_argument("--limit", type=int, default=DEFAULTS.page_size)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    counts = run(intervention=args.intervention, status=args.status, limit=args.limit)
    print(
        f"ClinicalTrials.gov ingestion complete: "
        f"{counts['new']} new, {counts['updated']} updated, {counts['unchanged']} unchanged"
    )


if __name__ == "__main__":
    main()
