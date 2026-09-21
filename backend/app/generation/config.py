"""Defaults for grounded answer generation and trial comparison.

Mirrors app/retrieval/config.py's pattern: plain constants here,
secrets and provider choice (ANTHROPIC_API_KEY/ANTHROPIC_MODEL) live in
app.core.config since those need environment variables.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationDefaults:
    # Chunks retrieved as context for a single direct question.
    top_k_chunks: int = 8
    max_tokens: int = 1024
    # Cap on how many of a trial's chunks go into a comparison prompt —
    # comparison uses the trial's full document in chunk order (there's
    # no query to rank against), so this bounds prompt size rather than
    # ranking relevance.
    max_chunks_per_trial: int = 20


DEFAULTS = GenerationDefaults()
