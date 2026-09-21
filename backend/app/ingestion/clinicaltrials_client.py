"""Thin client for the ClinicalTrials.gov API v2.

API docs: https://clinicaltrials.gov/data-api/api

Only what Phase 2 needs: a paginated study search. The ``httpx.Client``
is injected so tests can swap in a ``httpx.MockTransport`` instead of
hitting the network (see tests/test_clinicaltrials_client.py).
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx

DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"


class ClinicalTrialsClient:
    def __init__(self, client: httpx.Client, base_url: str = DEFAULT_BASE_URL) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    def search_studies(
        self,
        *,
        intervention: str | None = None,
        condition: str | None = None,
        status: str | None = None,
        page_size: int = 10,
        max_results: int | None = None,
    ) -> Iterator[dict]:
        """Yield raw ``study`` objects matching the query, paginating via
        ``nextPageToken`` until ``max_results`` is reached (or results run
        out).
        """

        params: dict[str, str] = {"pageSize": str(page_size), "format": "json"}
        if intervention:
            params["query.intr"] = intervention
        if condition:
            params["query.cond"] = condition
        if status:
            params["filter.overallStatus"] = status

        yielded = 0
        page_token: str | None = None

        while True:
            request_params = dict(params)
            if page_token:
                request_params["pageToken"] = page_token

            response = self._client.get(f"{self._base_url}/studies", params=request_params)
            response.raise_for_status()
            payload = response.json()

            for study in payload.get("studies", []):
                yield study
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            page_token = payload.get("nextPageToken")
            if not page_token:
                return
