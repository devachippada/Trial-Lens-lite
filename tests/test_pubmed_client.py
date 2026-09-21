"""Tests for PubMedClient using httpx.MockTransport — no real network
calls. This is the "mocked API fixtures" test for the PubMed side of
ingestion.
"""

from pathlib import Path

import httpx

from app.ingestion.pubmed_client import PubMedClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XML = (FIXTURES_DIR / "pubmed_efetch_sample.xml").read_text()

TWO_ARTICLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation><PMID>1</PMID></MedlineCitation></PubmedArticle>
  <PubmedArticle><MedlineCitation><PMID>2</PMID></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


def _client_with_handler(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestESearch:
    def test_parses_idlist(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("esearch.fcgi")
            return httpx.Response(200, json={"esearchresult": {"idlist": ["99999999", "123"]}})

        with _client_with_handler(handler) as http_client:
            client = PubMedClient(http_client)
            pmids = client.esearch("pembrolizumab", retmax=10)

        assert pmids == ["99999999", "123"]

    def test_includes_optional_identification_params(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"esearchresult": {"idlist": []}})

        with _client_with_handler(handler) as http_client:
            client = PubMedClient(http_client, api_key="k123", contact_email="dev@example.com")
            client.esearch("x")

        assert seen["api_key"] == "k123"
        assert seen["email"] == "dev@example.com"


class TestEFetch:
    def test_efetch_raw_returns_full_text(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("efetch.fcgi")
            return httpx.Response(200, text=SAMPLE_XML)

        with _client_with_handler(handler) as http_client:
            client = PubMedClient(http_client)
            raw = client.efetch_raw(["99999999"])

        assert "<PubmedArticleSet>" in raw

    def test_efetch_raw_empty_pmids_makes_no_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("should not be called for an empty PMID list")

        with _client_with_handler(handler) as http_client:
            client = PubMedClient(http_client)
            assert client.efetch_raw([]) == ""

    def test_fetch_articles_splits_multi_article_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=TWO_ARTICLE_XML)

        with _client_with_handler(handler) as http_client:
            client = PubMedClient(http_client)
            results = client.fetch_articles(["1", "2"])

        assert [pmid for pmid, _, _ in results] == ["1", "2"]
        for _, article_xml, element in results:
            assert "<PubmedArticle>" in article_xml
            assert element.tag == "PubmedArticle"

    def test_fetch_articles_single_article_matches_normalize_input(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=SAMPLE_XML)

        with _client_with_handler(handler) as http_client:
            client = PubMedClient(http_client)
            [(pmid, article_xml, element)] = client.fetch_articles(["99999999"])

        assert pmid == "99999999"
        assert element.findtext(".//ArticleTitle").startswith("Example Drug versus placebo")
