"""Pure IR/citation evaluation metrics — no I/O, no third-party imports.

Every function here takes plain Python data (lists/sets of source
identifiers, or plain booleans) and returns a float, so the whole module
is directly unit-testable without a database, an API key, or network
access — the same dependency-free-core pattern used throughout this
project (see app/retrieval/chunking.py, app/retrieval/fusion.py,
app/generation/citations.py).

Ground truth is always expressed at the *document* level: a set of
``source_identifier`` strings (an ``nct_id`` or ``pmid``) that a question
should be answered from. That matches how the Phase 6 fixture corpus is
built — see data/evaluation/questions.json's ``relevant_source_identifiers``
— and how retrieval results/citations are labeled
(``RetrievalResult.source_identifier`` / ``CitationOut.source_identifier``
both already carry this).

All edge-case conventions below (behavior when ``relevant`` or ``cited``
is empty) are deliberate design choices, documented inline, and covered
by tests/test_evaluation_metrics.py — not incidental behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


def recall_at_k(retrieved: list[str], relevant: set[str] | list[str], k: int) -> float:
    """Fraction of ``relevant`` identifiers present anywhere in the top ``k``
    of ``retrieved`` (rank-ordered, best first).

    Convention: if ``relevant`` is empty, there is nothing to recall, so
    this returns 1.0 (vacuously satisfied) rather than dividing by zero.
    Callers evaluating an abstention "trap" question (empty ground truth
    by construction) should not feed it to this function at all — recall
    isn't a meaningful score for "the system should have found nothing";
    use ``abstention_accuracy`` for those instead. This convention exists
    so a bug that accidentally calls this on an empty-ground-truth
    question doesn't silently score it as a *retrieval failure* (0.0)
    when the honest answer is "not applicable".
    """

    if k < 0:
        raise ValueError("k must be non-negative")

    relevant_set = set(relevant)
    if not relevant_set:
        return 1.0

    top_k = set(retrieved[:k])
    return len(top_k & relevant_set) / len(relevant_set)


def reciprocal_rank(retrieved: list[str], relevant: set[str] | list[str]) -> float:
    """1 / (rank of the first relevant identifier in ``retrieved``), or 0.0
    if none of ``relevant`` appears anywhere in ``retrieved``.

    Rank is 1-based raw list position (the first element is rank 1),
    matching the convention already used by
    ``app.retrieval.fusion.reciprocal_rank_fusion``.

    Convention: if ``relevant`` is empty, this returns 0.0. Unlike
    ``recall_at_k``, there is no natural "vacuously satisfied" reading
    here — reciprocal rank measures how quickly a relevant item was
    found, and with nothing relevant to find, "how quickly" is undefined.
    As with ``recall_at_k``, this function is meant to be called only on
    questions with non-empty ground truth (``mean_reciprocal_rank`` below
    documents the same expectation for the aggregate).
    """

    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0

    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def mean_recall_at_k(pairs: list[tuple[list[str], set[str] | list[str]]], k: int) -> float:
    """Mean of ``recall_at_k`` over a list of ``(retrieved, relevant)`` pairs.

    Raises ``ValueError`` on an empty list rather than returning a
    silent 0.0/1.0 that could be mistaken for a real score computed over
    zero questions.
    """

    if not pairs:
        raise ValueError("mean_recall_at_k requires at least one (retrieved, relevant) pair")
    return sum(recall_at_k(retrieved, relevant, k) for retrieved, relevant in pairs) / len(pairs)


def mean_reciprocal_rank(pairs: list[tuple[list[str], set[str] | list[str]]]) -> float:
    """Mean Reciprocal Rank over a list of ``(retrieved, relevant)`` pairs.

    Callers should only pass pairs with non-empty ``relevant`` (i.e.
    answerable questions with real ground truth) — see
    ``reciprocal_rank``'s docstring for why an empty-ground-truth
    question isn't meaningful input to this metric.
    """

    if not pairs:
        raise ValueError("mean_reciprocal_rank requires at least one (retrieved, relevant) pair")
    return sum(reciprocal_rank(retrieved, relevant) for retrieved, relevant in pairs) / len(pairs)


def citation_correctness(cited: list[str], relevant: set[str] | list[str]) -> float:
    """Precision of a generated answer's citations: what fraction of the
    identifiers it actually cited were truly relevant to the question.

    Convention when ``cited`` is empty (the answer cited nothing): 1.0 if
    nothing was relevant either (correctly citing nothing), else 0.0
    (it should have cited something and didn't). This mirrors
    ``app.generation.validation``'s own fail-closed philosophy: an
    unsupported answer is treated as wrong, not as "not applicable".
    """

    relevant_set = set(relevant)
    cited_set = set(cited)

    if not cited_set:
        return 1.0 if not relevant_set else 0.0

    return len(cited_set & relevant_set) / len(cited_set)


def citation_completeness(cited: list[str], relevant: set[str] | list[str]) -> float:
    """Recall of a generated answer's citations: what fraction of the
    truly relevant identifiers actually got cited.

    Convention: if ``relevant`` is empty, there was nothing to cite, so
    this returns 1.0 regardless of what was cited (same "nothing to find"
    reasoning as ``recall_at_k``).
    """

    relevant_set = set(relevant)
    if not relevant_set:
        return 1.0

    cited_set = set(cited)
    return len(cited_set & relevant_set) / len(relevant_set)


def abstention_accuracy(predictions: list[tuple[bool, bool]]) -> float:
    """Fraction of ``(expected_answerable, actually_answered)`` pairs that
    agree — i.e. the system answered exactly the questions it should have
    and abstained on exactly the ones it should have.

    Raises ``ValueError`` on an empty list for the same reason as
    ``mean_recall_at_k``/``mean_reciprocal_rank``: a silent default score
    for zero predictions could be mistaken for a real result.
    """

    if not predictions:
        raise ValueError("abstention_accuracy requires at least one prediction")
    correct = sum(1 for expected, actual in predictions if expected == actual)
    return correct / len(predictions)


@dataclass(frozen=True)
class ConfusionCounts:
    """Binary confusion matrix for the abstention decision, from the
    system's point of view: "positive" means "the system answered".
    """

    true_positive: int  # expected answerable, system answered
    false_positive: int  # expected abstain, system answered anyway
    true_negative: int  # expected abstain, system abstained
    false_negative: int  # expected answerable, system abstained (missed)

    @property
    def total(self) -> int:
        return self.true_positive + self.false_positive + self.true_negative + self.false_negative

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            raise ValueError("ConfusionCounts.accuracy requires at least one prediction")
        return (self.true_positive + self.true_negative) / self.total


def abstention_confusion_counts(predictions: list[tuple[bool, bool]]) -> ConfusionCounts:
    """Break ``abstention_accuracy``'s input down into a confusion matrix,
    so a report can show *how* the system was wrong (over-answering a
    trap question is a materially different, more concerning failure
    than being unnecessarily cautious on an answerable one), not just an
    aggregate accuracy number.
    """

    tp = fp = tn = fn = 0
    for expected, actual in predictions:
        if expected and actual:
            tp += 1
        elif not expected and actual:
            fp += 1
        elif not expected and not actual:
            tn += 1
        else:  # expected and not actual
            fn += 1
    return ConfusionCounts(true_positive=tp, false_positive=fp, true_negative=tn, false_negative=fn)
