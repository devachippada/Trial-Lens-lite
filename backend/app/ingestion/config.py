"""Defaults for the "small curated dataset" ingestion targets.

Deliberately query-based rather than a hardcoded list of specific NCT
IDs/PMIDs: a curated *topic* (a drug name that's well represented on both
ClinicalTrials.gov and PubMed) is safer than us hand-picking identifiers
from memory, which risks baking in wrong/stale IDs. Whoever runs the
ingestion scripts fetches whatever the live APIs currently return for
this query — nothing about specific trials or publications is asserted
here, only the search topic and how many results count as "small".
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionDefaults:
    ctgov_query_intervention: str = "pembrolizumab"
    ctgov_query_status: str = "COMPLETED"
    pubmed_query_term: str = "pembrolizumab AND clinical trial[pt]"
    page_size: int = 10


DEFAULTS = IngestionDefaults()
