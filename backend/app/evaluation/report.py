"""Evaluation report: a plain-data result container plus a Markdown
renderer. No I/O beyond returning a string — ``run_eval.py`` decides
where that string goes (stdout, a file under docs/).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evaluation.metrics import (
    abstention_accuracy,
    abstention_confusion_counts,
    citation_completeness,
    citation_correctness,
    recall_at_k,
    reciprocal_rank,
)


@dataclass(frozen=True)
class QuestionResult:
    """Everything observed for one evaluated question, plus its
    per-question metric values. ``recall_at_5``/``reciprocal_rank_`` are
    ``None`` for abstention-trap questions (not a meaningful score — see
    app/evaluation/metrics.py's docstrings on why those functions expect
    non-empty ground truth).
    """

    question_id: str
    question: str
    expect_answerable: bool
    relevant_source_identifiers: tuple[str, ...]
    retrieved_source_identifiers: tuple[str, ...]
    actual_status: str  # "answered" / "insufficient_evidence" / "validation_failed"
    cited_source_identifiers: tuple[str, ...]
    recall_at_5: float | None
    reciprocal_rank_: float | None
    citation_correctness_: float | None
    citation_completeness_: float | None

    @property
    def answered(self) -> bool:
        return self.actual_status == "answered"


def build_question_result(
    *,
    question_id: str,
    question: str,
    expect_answerable: bool,
    relevant_source_identifiers: tuple[str, ...],
    retrieved_source_identifiers: tuple[str, ...],
    actual_status: str,
    cited_source_identifiers: tuple[str, ...],
) -> QuestionResult:
    """Compute every per-question metric from raw observations, so
    callers (the real run_eval.py, or a test) only ever supply what was
    actually observed and never compute a metric value themselves.
    """

    has_ground_truth = bool(relevant_source_identifiers)
    recall_5 = (
        recall_at_k(list(retrieved_source_identifiers), set(relevant_source_identifiers), k=5)
        if has_ground_truth
        else None
    )
    rr = (
        reciprocal_rank(list(retrieved_source_identifiers), set(relevant_source_identifiers))
        if has_ground_truth
        else None
    )
    answered = actual_status == "answered"
    correctness = (
        citation_correctness(list(cited_source_identifiers), set(relevant_source_identifiers))
        if answered
        else None
    )
    completeness = (
        citation_completeness(list(cited_source_identifiers), set(relevant_source_identifiers))
        if answered
        else None
    )

    return QuestionResult(
        question_id=question_id,
        question=question,
        expect_answerable=expect_answerable,
        relevant_source_identifiers=relevant_source_identifiers,
        retrieved_source_identifiers=retrieved_source_identifiers,
        actual_status=actual_status,
        cited_source_identifiers=cited_source_identifiers,
        recall_at_5=recall_5,
        reciprocal_rank_=rr,
        citation_correctness_=correctness,
        citation_completeness_=completeness,
    )


@dataclass(frozen=True)
class EvaluationReport:
    generated_at: str
    claude_client_kind: str  # e.g. "real (claude-sonnet-4-5)" or "scripted-fake (self-test only)"
    embedding_provider_kind: str  # e.g. "hashing" or "voyage"
    retrieval_mode: str  # "hybrid", "fulltext", or "dense"
    question_results: list[QuestionResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def answerable_results(self) -> list[QuestionResult]:
        return [r for r in self.question_results if r.expect_answerable]

    @property
    def trap_results(self) -> list[QuestionResult]:
        return [r for r in self.question_results if not r.expect_answerable]

    def _mean(self, values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @property
    def mean_recall_at_5(self) -> float | None:
        return self._mean([r.recall_at_5 for r in self.answerable_results if r.recall_at_5 is not None])

    @property
    def mrr(self) -> float | None:
        return self._mean(
            [r.reciprocal_rank_ for r in self.answerable_results if r.reciprocal_rank_ is not None]
        )

    @property
    def mean_citation_correctness(self) -> float | None:
        return self._mean(
            [r.citation_correctness_ for r in self.question_results if r.citation_correctness_ is not None]
        )

    @property
    def mean_citation_completeness(self) -> float | None:
        return self._mean(
            [
                r.citation_completeness_
                for r in self.question_results
                if r.citation_completeness_ is not None
            ]
        )

    @property
    def abstention_accuracy_value(self) -> float | None:
        preds = [(r.expect_answerable, r.answered) for r in self.question_results]
        return abstention_accuracy(preds) if preds else None

    @property
    def abstention_confusion(self):
        preds = [(r.expect_answerable, r.answered) for r in self.question_results]
        return abstention_confusion_counts(preds) if preds else None


def _fmt(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


def render_markdown(report: EvaluationReport) -> str:
    lines = [
        "# TrialLens Lite — Evaluation Report",
        "",
        f"Generated: {report.generated_at}",
        f"Claude client: {report.claude_client_kind}",
        f"Embedding provider: {report.embedding_provider_kind}",
        f"Retrieval mode: {report.retrieval_mode}",
        f"Questions evaluated: {len(report.question_results)} "
        f"({len(report.answerable_results)} answerable, {len(report.trap_results)} abstention traps)",
        "",
        "## Summary metrics",
        "",
        f"- Recall@5 (mean over answerable questions): {_fmt(report.mean_recall_at_5)}",
        f"- MRR (mean reciprocal rank, answerable questions): {_fmt(report.mrr)}",
        f"- Citation correctness (precision, mean over answered questions): {_fmt(report.mean_citation_correctness)}",
        f"- Citation completeness (recall, mean over answered questions): {_fmt(report.mean_citation_completeness)}",
        f"- Abstention accuracy (all 20 questions): {_fmt(report.abstention_accuracy_value)}",
    ]

    confusion = report.abstention_confusion
    if confusion is not None:
        lines += [
            f"  - True positives (answered correctly): {confusion.true_positive}",
            f"  - False positives (answered a trap question — most concerning failure mode): {confusion.false_positive}",
            f"  - True negatives (abstained correctly on a trap): {confusion.true_negative}",
            f"  - False negatives (abstained on an answerable question): {confusion.false_negative}",
        ]

    if report.notes:
        lines += ["", "## Notes"]
        for note in report.notes:
            lines.append(f"- {note}")

    lines += ["", "## Per-question results", "", "| ID | Expect answerable | Status | Recall@5 | RR | Correctness | Completeness |", "|---|---|---|---|---|---|---|"]
    for r in report.question_results:
        lines.append(
            f"| {r.question_id} | {r.expect_answerable} | {r.actual_status} | "
            f"{_fmt(r.recall_at_5)} | {_fmt(r.reciprocal_rank_)} | "
            f"{_fmt(r.citation_correctness_)} | {_fmt(r.citation_completeness_)} |"
        )

    return "\n".join(lines) + "\n"
