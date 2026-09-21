"""Loading and validating the Phase 6 evaluation question set.

``data/evaluation/questions.json`` is a hand-authored ground-truth set
against the synthetic corpus in ``data/evaluation/fixtures_ctgov.json``
and ``fixtures_pubmed.xml`` (see that JSON file's own ``_fixture_note``
for how ground truth was derived and why it isn't a fabricated number in
the sense Phase 6's "do not invent metrics" instruction means). This
module only parses and validates the JSON — it has no opinion about
where the file lives beyond a sensible default, so a test can point it
at a different path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.evaluation.paths import DEFAULT_QUESTIONS_PATH

__all__ = ["DEFAULT_QUESTIONS_PATH", "EvalQuestion", "load_questions", "validate_questions"]


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    expect_answerable: bool
    relevant_source_identifiers: tuple[str, ...]
    ground_truth_basis: str


def load_questions(path: Path = DEFAULT_QUESTIONS_PATH) -> list[EvalQuestion]:
    """Parse ``questions.json`` into a list of :class:`EvalQuestion`."""

    data = json.loads(Path(path).read_text())
    questions = []
    for raw in data["questions"]:
        questions.append(
            EvalQuestion(
                id=raw["id"],
                question=raw["question"],
                expect_answerable=raw["expect_answerable"],
                relevant_source_identifiers=tuple(raw["relevant_source_identifiers"]),
                ground_truth_basis=raw.get("ground_truth_basis", ""),
            )
        )
    return questions


def validate_questions(
    questions: list[EvalQuestion], known_source_identifiers: set[str]
) -> list[str]:
    """Return a list of human-readable problems found in ``questions``
    (empty if none). Checks internal shape/consistency and — given the
    set of ``source_identifier`` values actually present in the seeded
    corpus — referential integrity, so a typo'd NCT/PMID in the dataset
    itself is caught here rather than silently scored as a retrieval
    failure.
    """

    problems: list[str] = []
    seen_ids: set[str] = set()

    for q in questions:
        if q.id in seen_ids:
            problems.append(f"duplicate question id: {q.id!r}")
        seen_ids.add(q.id)

        if not q.question.strip():
            problems.append(f"{q.id}: question text is empty")

        if q.expect_answerable and not q.relevant_source_identifiers:
            problems.append(
                f"{q.id}: expect_answerable=True but relevant_source_identifiers is empty"
            )
        if not q.expect_answerable and q.relevant_source_identifiers:
            problems.append(
                f"{q.id}: expect_answerable=False but relevant_source_identifiers is non-empty "
                "(a trap question should have no ground-truth source)"
            )

        for identifier in q.relevant_source_identifiers:
            if identifier not in known_source_identifiers:
                problems.append(
                    f"{q.id}: relevant_source_identifiers references unknown identifier {identifier!r}"
                )

    answerable_count = sum(1 for q in questions if q.expect_answerable)
    trap_count = len(questions) - answerable_count
    if len(questions) != 20:
        problems.append(f"expected 20 questions total, found {len(questions)}")
    if answerable_count != 15:
        problems.append(f"expected 15 answerable questions, found {answerable_count}")
    if trap_count != 5:
        problems.append(f"expected 5 abstention-trap questions, found {trap_count}")

    return problems
