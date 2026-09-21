"""Thin client for PubMed E-utilities (ESearch + EFetch).

API docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/

Only what Phase 2 needs: search for PMIDs, then fetch full records for
them. The ``httpx.Client`` is injected so tests can swap in a
``httpx.MockTransport`` (see tests/test_pubmed_client.py). NCBI asks
callers to identify themselves and (ideally) supply an API key — both
are optional here and simply omitted from the request if not set.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

DEFAULT_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        contact_email: str | None = None,
        tool_name: str = "trial-lens-lite",
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._contact_email = contact_email
        self._tool_name = tool_name

    def _common_params(self) -> dict[str, str]:
        params = {"db": "pubmed", "tool": self._tool_name}
        if self._api_key:
            params["api_key"] = self._api_key
        if self._contact_email:
            params["email"] = self._contact_email
        return params

    def esearch(self, term: str, retmax: int = 10) -> list[str]:
        """Return a list of PMIDs matching ``term``."""

        params = {**self._common_params(), "term": term, "retmax": str(retmax), "retmode": "json"}
        response = self._client.get(f"{self._base_url}/esearch.fcgi", params=params)
        response.raise_for_status()
        payload = response.json()
        return list(payload.get("esearchresult", {}).get("idlist", []))

    def efetch_raw(self, pmids: list[str]) -> str:
        """Return the raw EFetch XML response (``PubmedArticleSet``) for
        the given PMIDs, as a single string.
        """

        if not pmids:
            return ""

        params = {
            **self._common_params(),
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "xml",
        }
        response = self._client.get(f"{self._base_url}/efetch.fcgi", params=params)
        response.raise_for_status()
        return response.text

    def fetch_articles(self, pmids: list[str]) -> list[tuple[str, str, ET.Element]]:
        """Fetch and split an EFetch response into per-article pieces.

        Returns a list of ``(pmid, article_xml, article_element)`` tuples
        — ``article_xml`` is the serialized XML for just that one
        ``PubmedArticle`` (used for hashing/raw storage), separate from
        the full multi-article response.
        """

        raw_xml = self.efetch_raw(pmids)
        if not raw_xml:
            return []

        root = ET.fromstring(raw_xml)
        results = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID") or ""
            article_xml = ET.tostring(article, encoding="unicode")
            results.append((pmid, article_xml, article))
        return results
