"""Configurable embedding provider.

``get_embedding_provider`` picks an implementation from
``settings.embedding_provider``:

- ``"hashing"`` (default) — :class:`HashingEmbeddingProvider`. Zero
  dependencies, no network, no API key, fully deterministic. It is
  *not* semantically meaningful (see its docstring) — it exists so the
  whole pipeline (chunk -> embed -> store -> cosine search) can be
  built, tested, and demoed without any external service, and so this
  environment could actually verify the plumbing without network
  access to a real embeddings API.
- ``"voyage"`` — :class:`VoyageEmbeddingProvider`, a real HTTP-based
  provider. Anthropic recommends Voyage AI for embeddings (Claude
  itself doesn't expose an embeddings endpoint), so it's the natural
  "real" provider to pair with the Claude SDK used elsewhere in this
  project.

Both implement the same tiny :class:`EmbeddingProvider` protocol, so
swapping one for the other is a config change, not a code change.
"""

from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import httpx

# httpx is only actually imported (below, lazily) inside VoyageEmbeddingProvider
# and get_embedding_provider's "voyage" branch. That keeps this module —
# and HashingEmbeddingProvider in particular — importable and usable with
# zero third-party dependencies when no real HTTP-based provider is
# configured.


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, same order."""
        ...


class HashingEmbeddingProvider:
    """Deterministic feature-hashing embedding (a real, if weak, technique
    — see e.g. the "hashing trick" used in Vowpal Wabbit) rather than a
    fabricated stand-in.

    Each whitespace-separated token is hashed into one of ``dimension``
    buckets with a random sign (both derived from the token's SHA-256
    digest), and the resulting vector is L2-normalized. Identical text
    always embeds identically; completely different vocabulary embeds
    into (mostly) different buckets. It captures none of the actual
    *meaning* a trained model would, so dense-retrieval quality with
    this provider is weak by design — swap in a real provider for
    anything beyond exercising the pipeline mechanics.
    """

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            digest_int = int.from_bytes(digest, "big")
            index = digest_int % self.dimension
            sign = 1.0 if (digest_int // self.dimension) % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]


class VoyageEmbeddingProvider:
    """Real embeddings via the Voyage AI HTTP API.

    Endpoint/field names are per Voyage's documented embeddings API
    (https://docs.voyageai.com/reference/embeddings-api) as of when this
    was written; this environment has no network access to Voyage to
    exercise it live, so if a field has since changed, check that page
    first. ``output_dimension`` relies on Voyage's newer large models
    supporting configurable (Matryoshka-style) output width so it can
    match whatever ``chunks.embedding`` column width this project is
    using — verify your chosen model supports it.
    """

    API_URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        model: str = "voyage-3-large",
        dimension: int = 256,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._client.post(
            self.API_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "input": texts,
                "model": self._model,
                "output_dimension": self.dimension,
                "input_type": "document",
            },
        )
        response.raise_for_status()
        payload = response.json()
        # Voyage returns `data` in input order per their docs; sort by
        # `index` defensively in case that ever isn't guaranteed.
        items = sorted(payload["data"], key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in items]


def get_embedding_provider(settings, http_client: httpx.Client | None = None) -> EmbeddingProvider:
    """Factory selecting a provider from ``settings.embedding_provider``."""

    if settings.embedding_provider == "voyage":
        if not settings.voyage_api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=voyage requires VOYAGE_API_KEY to be set"
            )
        import httpx  # lazy: only needed for this provider, see module docstring

        return VoyageEmbeddingProvider(
            client=http_client or httpx.Client(timeout=30.0),
            api_key=settings.voyage_api_key,
            model=settings.voyage_model,
            dimension=settings.embedding_dimension,
        )

    if settings.embedding_provider != "hashing":
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER {settings.embedding_provider!r}; "
            "expected 'hashing' or 'voyage'"
        )

    return HashingEmbeddingProvider(dimension=settings.embedding_dimension)
