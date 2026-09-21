"""Tests for ClinicalTrialsClient using httpx.MockTransport — no real
network calls. This is the "mocked API fixtures" test for the
ClinicalTrials.gov side of ingestion.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.ingestion.clinicaltrials_client import ClinicalTrialsClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ctgov_raw() -> dict:
    return json.loads((FIXTURES_DIR / "ctgov_study_sample.json").read_text())


def _client_with_handler(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestSearchStudies:
    def test_single_page(self, ctgov_raw):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v2/studies"
            params = parse_qs(request.url.query.decode())
            assert params["query.intr"] == ["pembrolizumab"]
            return httpx.Response(200, json={"studies": [ctgov_raw], "nextPageToken": None})

        with _client_with_handler(handler) as http_client:
            client = ClinicalTrialsClient(http_client)
            studies = list(client.search_studies(intervention="pembrolizumab"))

        assert len(studies) == 1
        assert studies[0]["protocolSection"]["identificationModule"]["nctId"] == "NCT99999999"

    def test_paginates_until_no_next_token(self, ctgov_raw):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            params = parse_qs(request.url.query.decode())
            calls.append(params.get("pageToken"))
            if "pageToken" not in params:
                return httpx.Response(200, json={"studies": [ctgov_raw], "nextPageToken": "page2"})
            return httpx.Response(200, json={"studies": [ctgov_raw], "nextPageToken": None})

        with _client_with_handler(handler) as http_client:
            client = ClinicalTrialsClient(http_client)
            studies = list(client.search_studies(intervention="pembrolizumab"))

        assert len(studies) == 2
        assert len(calls) == 2

    def test_stops_at_max_results(self, ctgov_raw):
        def handler(request: httpx.Request) -> httpx.Response:
            # Return three studies in one page; max_results should cut us
            # off at two without a second request.
            return httpx.Response(
                200, json={"studies": [ctgov_raw, ctgov_raw, ctgov_raw], "nextPageToken": "more"}
            )

        with _client_with_handler(handler) as http_client:
            client = ClinicalTrialsClient(http_client)
            studies = list(client.search_studies(intervention="x", max_results=2))

        assert len(studies) == 2

    def test_raises_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        with _client_with_handler(handler) as http_client:
            client = ClinicalTrialsClient(http_client)
            with pytest.raises(httpx.HTTPStatusError):
                list(client.search_studies(intervention="x"))
