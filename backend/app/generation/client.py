"""Thin wrapper around the Anthropic Claude Messages API.

Kept as small as possible and behind a tiny ``ClaudeClient`` protocol so
the rest of ``app/generation/`` can be tested against a fake
implementation, with no ``anthropic`` package installed and no network
access — see ``tests/test_claude_client.py`` and the fakes used
throughout the other generation tests. ``anthropic`` itself is only
imported lazily, inside ``get_claude_client``'s real-client branch, the
same pattern used for ``httpx`` in ``app/retrieval/embeddings.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import anthropic


@dataclass(frozen=True)
class ClaudeResponse:
    text: str


class ClaudeClient(Protocol):
    def complete(self, *, system: str, user: str, max_tokens: int) -> ClaudeResponse: ...


class AnthropicClaudeClient:
    """Real implementation, backed by the ``anthropic`` Python SDK.

    Takes an already-constructed SDK client rather than an API key, so
    it only ever duck-types against ``client.messages.create(...)`` —
    that's what lets ``tests/test_claude_client.py`` exercise this
    class's actual response-parsing logic with a plain fake object,
    without the real package installed.
    """

    def __init__(self, client: "anthropic.Anthropic", model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> ClaudeResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # A text-only response (no tool use) is one or more TextBlocks;
        # concatenate defensively in case the SDK ever splits one.
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return ClaudeResponse(text=text)


def get_claude_client(settings) -> ClaudeClient:
    """Factory selecting/constructing the real Claude client from settings.

    Raises ``RuntimeError`` rather than silently falling back to
    anything — there's no dependency-free "fake" answer-generation
    provider analogous to ``HashingEmbeddingProvider``, because a fake
    LLM response would defeat the entire point of grounded generation.
    """

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set to use Claude-backed answer generation")

    import anthropic  # lazy: only needed for the real client, see module docstring

    return AnthropicClaudeClient(
        client=anthropic.Anthropic(api_key=settings.anthropic_api_key),
        model=settings.anthropic_model,
    )
