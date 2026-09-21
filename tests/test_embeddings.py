"""Tests for the configurable embedding provider (app/retrieval/embeddings.py).

HashingEmbeddingProvider is dependency-free and tested directly. The
Voyage HTTP provider is tested with httpx.MockTransport (same pattern
as test_clinicaltrials_client.py / test_pubmed_client.py) — no real
network calls are made.
"""

import math
from types import SimpleNamespace

import httpx
import pytest

from app.retrieval.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    VoyageEmbeddingProvider,
    get_embedding_provider,
)


class TestHashingEmbeddingProvider:
    def test_dimension_matches_configured_value(self):
        provider = HashingEmbeddingProvider(dimension=32)

        [vector] = provider.embed(["some clinical trial text"])

        assert len(vector) == 32

    def test_default_dimension_is_256(self):
        provider = HashingEmbeddingProvider()

        assert provider.dimension == 256

    def test_same_text_always_embeds_identically(self):
        provider = HashingEmbeddingProvider(dimension=64)

        first = provider.embed(["pembrolizumab overall survival"])
        second = provider.embed(["pembrolizumab overall survival"])

        assert first == second

    def test_is_case_insensitive(self):
        provider = HashingEmbeddingProvider(dimension=64)

        [lower] = provider.embed(["overall survival endpoint"])
        [upper] = provider.embed(["Overall Survival Endpoint"])

        assert lower == upper

    def test_different_text_embeds_differently(self):
        provider = HashingEmbeddingProvider(dimension=64)

        [a] = provider.embed(["progression free survival"])
        [b] = provider.embed(["adverse event rate"])

        assert a != b

    def test_nonempty_text_is_l2_normalized(self):
        provider = HashingEmbeddingProvider(dimension=64)

        [vector] = provider.embed(["a reasonably long sentence with several tokens in it"])

        norm = math.sqrt(sum(v * v for v in vector))
        assert norm == pytest.approx(1.0)

    def test_empty_string_embeds_to_the_zero_vector(self):
        provider = HashingEmbeddingProvider(dimension=16)

        [vector] = provider.embed([""])

        assert vector == [0.0] * 16

    def test_embed_preserves_order_and_batches_independently(self):
        provider = HashingEmbeddingProvider(dimension=32)

        batch = provider.embed(["alpha", "beta"])
        solo_alpha = provider.embed(["alpha"])
        solo_beta = provider.embed(["beta"])

        assert batch[0] == solo_alpha[0]
        assert batch[1] == solo_beta[0]

    def test_satisfies_embedding_provider_protocol_shape(self):
        provider: EmbeddingProvider = HashingEmbeddingProvider(dimension=8)

        assert hasattr(provider, "dimension")
        assert callable(provider.embed)


def _mock_voyage_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestVoyageEmbeddingProvider:
    def test_posts_expected_payload_and_parses_response(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0.2, 0.3]},
                        {"index": 0, "embedding": [0.1, 0.1]},
                    ]
                },
            )

        with _mock_voyage_client(handler) as http_client:
            provider = VoyageEmbeddingProvider(
                client=http_client, api_key="test-key", model="voyage-3-large", dimension=2
            )
            vectors = provider.embed(["first text", "second text"])

        assert captured["url"] == VoyageEmbeddingProvider.API_URL
        assert captured["auth"] == "Bearer test-key"
        assert captured["body"] == {
            "input": ["first text", "second text"],
            "model": "voyage-3-large",
            "output_dimension": 2,
            "input_type": "document",
        }
        # Response came back out of order (index 1 before index 0); the
        # provider must sort by `index` before returning.
        assert vectors == [[0.1, 0.1], [0.2, 0.3]]

    def test_empty_input_makes_no_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("should not have made an HTTP request for empty input")

        with _mock_voyage_client(handler) as http_client:
            provider = VoyageEmbeddingProvider(client=http_client, api_key="test-key")
            assert provider.embed([]) == []

    def test_raises_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid api key"})

        with _mock_voyage_client(handler) as http_client:
            provider = VoyageEmbeddingProvider(client=http_client, api_key="bad-key")
            with pytest.raises(httpx.HTTPStatusError):
                provider.embed(["text"])


class TestGetEmbeddingProviderFactory:
    def _settings(self, **overrides):
        defaults = dict(
            embedding_provider="hashing",
            embedding_dimension=256,
            voyage_api_key=None,
            voyage_model="voyage-3-large",
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_defaults_to_hashing_provider(self):
        provider = get_embedding_provider(self._settings(embedding_provider="hashing", embedding_dimension=48))

        assert isinstance(provider, HashingEmbeddingProvider)
        assert provider.dimension == 48

    def test_voyage_without_api_key_raises(self):
        settings = self._settings(embedding_provider="voyage", voyage_api_key=None)

        with pytest.raises(RuntimeError):
            get_embedding_provider(settings)

    def test_voyage_with_api_key_returns_wired_provider(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

        settings = self._settings(
            embedding_provider="voyage",
            voyage_api_key="abc123",
            voyage_model="voyage-3-large",
            embedding_dimension=2,
        )

        with _mock_voyage_client(handler) as http_client:
            provider = get_embedding_provider(settings, http_client=http_client)

            assert isinstance(provider, VoyageEmbeddingProvider)
            assert provider.embed(["hello"]) == [[0.5, 0.5]]

    def test_unknown_provider_raises_value_error(self):
        settings = self._settings(embedding_provider="not-a-real-provider")

        with pytest.raises(ValueError):
            get_embedding_provider(settings)
