"""FastAPI ``Depends()`` wrappers around the settings/embedding-provider/
Claude-client factories used by the retrieval and Q&A routes.

Phases 3-4 wrote ``app/api/retrieval.py`` and ``app/api/qa.py`` to call
``get_settings()`` / ``get_embedding_provider(settings)`` /
``get_claude_client(settings)`` as plain function calls inside each route
handler body. That was fine for production (``get_settings()`` is
``lru_cache``'d, so it's cheap and stable) but it left no seam for
``app.dependency_overrides`` — FastAPI's standard mechanism for
substituting a fake in tests — to hook into: overriding a plain function
call inside a handler body requires monkeypatching the imported name
instead, exactly the kind of test-only workaround this project has
avoided everywhere else (see ``app/generation/answer.py``'s docstring on
why ``retrieve``/``claude_client`` are passed in as parameters rather
than imported).

This module makes those same three factories available as
``Depends()``-compatible callables, so ``tests/test_end_to_end.py`` can
swap in a scripted fake Claude client for the one call this project
genuinely cannot make in this sandbox (a real Anthropic API call) while
every other line of ``app/api/qa.py``/``app/api/retrieval.py`` runs
unmodified, real code against a real database. Production behavior is
byte-for-byte unchanged: with no override installed, FastAPI calls these
exactly once per request and they do exactly what the inline calls did
before this refactor — this file adds a seam, not new behavior.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.core.config import Settings, get_settings
from app.generation.client import ClaudeClient, get_claude_client
from app.retrieval.embeddings import EmbeddingProvider, get_embedding_provider


def get_settings_dependency() -> Settings:
    return get_settings()


def get_embedding_provider_dependency(
    settings: Settings = Depends(get_settings_dependency),
) -> EmbeddingProvider:
    return get_embedding_provider(settings)


def get_claude_client_dependency(
    settings: Settings = Depends(get_settings_dependency),
) -> ClaudeClient:
    try:
        return get_claude_client(settings)
    except RuntimeError as exc:
        # get_claude_client() raises a bare RuntimeError when no API key is
        # configured (see app/generation/client.py) - the right exception
        # type for its non-HTTP callers (scripts, tests), but wrong here:
        # an uncaught exception raised while resolving a FastAPI dependency
        # propagates past CORSMiddleware to Starlette's ServerErrorMiddleware,
        # which sits *outside* user-added middleware (including CORS) and
        # produces a bare 500 with no Access-Control-Allow-Origin header. A
        # cross-origin browser then can't read that response at all and
        # reports a generic network failure ("Failed to fetch") instead of
        # the actual "no API key configured" error. Converting it to an
        # HTTPException here routes the error response back through
        # Starlette's ExceptionMiddleware, which *is* inside CORSMiddleware,
        # so the browser gets a normal, readable, CORS-correct 503 instead.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
