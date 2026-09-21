"""Pure, dependency-free normalization for ClinicalTrials.gov and PubMed.

Everything in this module operates on plain Python data (dicts, XML
elements, strings) already fetched by the API clients. It does no I/O and
imports nothing beyond the standard library, so it can be unit-tested
without a database, network access, or any third-party package —
including in environments where SQLAlchemy/httpx/pytest can't be
installed.

Field names below follow the ClinicalTrials.gov API v2
(https://clinicaltrials.gov/data-api/api) and PubMed EFetch's
``PubmedArticle`` XML shape as documented by NCBI E-utilities. They are
extracted defensively (``.get`` chains, ``findtext`` with defaults) so a
missing/renamed field degrades to ``None`` rather than raising — but if
this is run against the live APIs and a field comes back empty that
shouldn't be, that mapping is the first thing to check against the
current API docs, since it was written from spec/memory rather than a
live response captured in this environment (see docs/phase-2-notes.md).
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

NCT_ID_PATTERN = re.compile(r"\bNCT\d{8}\b")


def sha256_hex(data: str) -> str:
    """SHA-256 hex digest of a string, encoded as UTF-8."""

    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_json(obj: object) -> str:
    """Deterministic JSON serialization used as input to content hashing.

    Sorted keys and fixed separators mean the same logical payload always
    hashes the same way, regardless of key order in the source API
    response.
    """

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _parse_partial_date(value: str) -> date | None:
    """Parse a ``YYYY``, ``YYYY-MM``, or ``YYYY-MM-DD`` string.

    Both ClinicalTrials.gov and PubMed frequently publish partial dates.
    Missing month/day default to 1 rather than being dropped, since a
    trial's registered "January 2021" start date is more useful as
    2021-01-01 than as no date at all — callers that need to distinguish
    "exact" from "year-only" dates should keep the original string too
    (we do, in ``raw_data``/``raw_xml``).
    """

    if not value:
        return None

    parts = value.strip().split("-")
    try:
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
    return None


def parse_ctgov_date(value: dict | str | None) -> date | None:
    """Parse a ClinicalTrials.gov "date struct" (``{"date": "...", ...}``)
    or a bare date string into a :class:`date`.
    """

    if value is None:
        return None
    if isinstance(value, str):
        return _parse_partial_date(value)
    if isinstance(value, dict):
        return _parse_partial_date(value.get("date", ""))
    return None


def extract_nct_ids(text: str | None) -> list[str]:
    """Find NCT numbers mentioned in free text (e.g. an abstract)."""

    if not text:
        return []
    # dict.fromkeys preserves first-seen order while de-duplicating.
    return list(dict.fromkeys(NCT_ID_PATTERN.findall(text)))


@dataclass
class NormalizedTrial:
    nct_id: str
    source_url: str
    brief_title: str
    official_title: str | None
    overall_status: str
    phase: str | None
    study_type: str | None
    conditions: list[str]
    intervention_names: list[str]
    sponsor_name: str | None
    enrollment_count: int | None
    start_date: date | None
    primary_completion_date: date | None
    completion_date: date | None
    last_update_posted_date: date | None
    brief_summary: str | None
    detailed_description: str | None
    primary_outcomes: list[dict]
    secondary_outcomes: list[dict]
    raw_data: dict
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = sha256_hex(canonical_json(self.raw_data))

    @property
    def document_text(self) -> str:
        parts = [p for p in (self.brief_summary, self.detailed_description) if p]
        return "\n\n".join(parts)


@dataclass
class NormalizedPublication:
    pmid: str
    source_url: str
    title: str
    doi: str | None
    journal: str | None
    publication_date: date | None
    publication_year: int | None
    authors: list[str]
    abstract: str | None
    mesh_terms: list[str]
    linked_nct_ids: list[str]
    raw_xml: str
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = sha256_hex(self.raw_xml)

    @property
    def document_text(self) -> str:
        return self.abstract or ""


def normalize_trial(raw: dict) -> NormalizedTrial:
    """Normalize one ClinicalTrials.gov API v2 ``study`` object."""

    protocol = raw.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    conditions_mod = protocol.get("conditionsModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
    description = protocol.get("descriptionModule", {})
    outcomes = protocol.get("outcomesModule", {})

    nct_id = identification.get("nctId", "")
    phases = design.get("phases") or []
    interventions = arms.get("interventions") or []

    return NormalizedTrial(
        nct_id=nct_id,
        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
        brief_title=identification.get("briefTitle", ""),
        official_title=identification.get("officialTitle"),
        overall_status=status.get("overallStatus", "UNKNOWN"),
        phase="/".join(phases) if phases else None,
        study_type=design.get("studyType"),
        conditions=list(conditions_mod.get("conditions") or []),
        intervention_names=[i.get("name") for i in interventions if i.get("name")],
        sponsor_name=(sponsor_mod.get("leadSponsor") or {}).get("name"),
        enrollment_count=(design.get("enrollmentInfo") or {}).get("count"),
        start_date=parse_ctgov_date(status.get("startDateStruct")),
        primary_completion_date=parse_ctgov_date(status.get("primaryCompletionDateStruct")),
        completion_date=parse_ctgov_date(status.get("completionDateStruct")),
        last_update_posted_date=parse_ctgov_date(status.get("lastUpdatePostDateStruct")),
        brief_summary=description.get("briefSummary"),
        detailed_description=description.get("detailedDescription"),
        primary_outcomes=list(outcomes.get("primaryOutcomes") or []),
        secondary_outcomes=list(outcomes.get("secondaryOutcomes") or []),
        raw_data=raw,
    )


def _findtext(element: ET.Element, path: str) -> str | None:
    text = element.findtext(path)
    return text.strip() if text else None


def _parse_pubmed_date(article: ET.Element) -> tuple[date | None, int | None]:
    """Best-effort date from ``ArticleDate`` or ``PubDate`` (Year/Month/Day or
    Medline free-text). Returns ``(date_or_none, year_or_none)``.
    """

    for path in (".//ArticleDate", ".//Journal/JournalIssue/PubDate"):
        node = article.find(path)
        if node is None:
            continue
        year_text = node.findtext("Year")
        if not year_text:
            medline_date = node.findtext("MedlineDate")
            year_match = re.match(r"(\d{4})", medline_date or "")
            year_text = year_match.group(1) if year_match else None
        if not year_text:
            continue
        month_text = node.findtext("Month") or "1"
        day_text = node.findtext("Day") or "1"
        month = _month_to_int(month_text)
        try:
            year = int(year_text)
            day = int(day_text)
            return date(year, month, day), year
        except ValueError:
            try:
                return None, int(year_text)
            except ValueError:
                return None, None
    return None, None


_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ],
        start=1,
    )
}


def _month_to_int(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return max(1, min(12, int(value)))
    return _MONTHS.get(value[:3].lower(), 1)


def normalize_publication(pmid: str, article_xml: str, article: ET.Element) -> NormalizedPublication:
    """Normalize one ``PubmedArticle`` element from an EFetch response.

    ``article_xml`` is the serialized XML for just this one article
    (used for the content hash / raw storage), and ``article`` is the
    already-parsed element for that same article.
    """

    title = _findtext(article, ".//ArticleTitle") or ""
    journal = _findtext(article, ".//Journal/Title")

    abstract_parts = []
    for node in article.findall(".//Abstract/AbstractText"):
        label = node.get("Label")
        text = "".join(node.itertext()).strip()
        if not text:
            continue
        abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(abstract_parts) if abstract_parts else None

    authors = []
    for author in article.findall(".//AuthorList/Author"):
        last = author.findtext("LastName")
        initials = author.findtext("Initials")
        collective = author.findtext("CollectiveName")
        if last:
            authors.append(f"{last} {initials}".strip() if initials else last)
        elif collective:
            authors.append(collective)

    doi = None
    for article_id in article.findall(".//ArticleIdList/ArticleId"):
        if article_id.get("IdType") == "doi" and article_id.text:
            doi = article_id.text.strip()
            break

    mesh_terms = [
        d.text.strip()
        for d in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName")
        if d.text
    ]

    linked_nct_ids = set()
    for accession in article.findall(".//DataBankList/DataBank/AccessionNumberList/AccessionNumber"):
        if accession.text and accession.text.strip().upper().startswith("NCT"):
            linked_nct_ids.add(accession.text.strip().upper())
    for si in article.findall(".//SecondarySourceId"):
        if si.text:
            linked_nct_ids.update(extract_nct_ids(si.text))
    linked_nct_ids.update(extract_nct_ids(title))
    linked_nct_ids.update(extract_nct_ids(abstract))

    pub_date, pub_year = _parse_pubmed_date(article)

    return NormalizedPublication(
        pmid=pmid,
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        title=title,
        doi=doi,
        journal=journal,
        publication_date=pub_date,
        publication_year=pub_year,
        authors=authors,
        abstract=abstract,
        mesh_terms=mesh_terms,
        linked_nct_ids=sorted(linked_nct_ids),
        raw_xml=article_xml,
    )
