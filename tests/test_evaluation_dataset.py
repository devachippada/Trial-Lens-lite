"""Tests for app/evaluation/dataset.py.

These validate the real data/evaluation/questions.json against the real
fixture corpus — no database needed: ``known_source_identifiers`` is
computed by running the real ``normalize_trial``/``normalize_publication``
functions directly over ``fixtures_ctgov.json``/``fixtures_pubmed.xml``,
the same way ``app.evaluation.seed_fixtures`` derives each Document's
``source_identifier``, just without a Session/database in the loop. That
makes this whole test file directly executable in this sandbox (see
docs/phase-6-notes.md), unlike the DB-backed evaluation/end-to-end
tests.
"""

import json
import xml.etree.ElementTree as ET

from app.evaluation.dataset import DEFAULT_QUESTIONS_PATH, EvalQuestion, load_questions, validate_questions
from app.evaluation.paths import DEFAULT_CTGOV_FIXTURES, DEFAULT_PUBMED_FIXTURES
from app.ingestion.normalize import normalize_publication, normalize_trial


def _known_source_identifiers() -> set[str]:
    ctgov = json.loads(DEFAULT_CTGOV_FIXTURES.read_text())
    nct_ids = {normalize_trial(s).nct_id for s in ctgov["studies"]}

    root = ET.fromstring(DEFAULT_PUBMED_FIXTURES.read_text())
    pmids = set()
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        article_xml = ET.tostring(article, encoding="unicode")
        pmids.add(normalize_publication(pmid, article_xml, article).pmid)

    return nct_ids | pmids


class TestLoadQuestions:
    def test_default_path_exists(self):
        assert DEFAULT_QUESTIONS_PATH.exists()

    def test_loads_20_questions(self):
        questions = load_questions()
        assert len(questions) == 20
        assert all(isinstance(q, EvalQuestion) for q in questions)

    def test_15_answerable_5_traps(self):
        questions = load_questions()
        answerable = [q for q in questions if q.expect_answerable]
        traps = [q for q in questions if not q.expect_answerable]
        assert len(answerable) == 15
        assert len(traps) == 5

    def test_question_ids_are_unique(self):
        questions = load_questions()
        ids = [q.id for q in questions]
        assert len(ids) == len(set(ids))


class TestValidateQuestionsAgainstRealCorpus:
    def test_real_dataset_has_no_problems(self):
        questions = load_questions()
        problems = validate_questions(questions, _known_source_identifiers())
        assert problems == []

    def test_every_known_identifier_is_referenced_by_at_least_one_question(self):
        # Not a validate_questions check, but a real coverage property of
        # this specific dataset worth locking in: every fixture document
        # is ground truth for at least one answerable question.
        questions = load_questions()
        referenced = {i for q in questions for i in q.relevant_source_identifiers}
        assert referenced == _known_source_identifiers()


class TestValidateQuestionsSyntheticCases:
    def test_flags_duplicate_ids(self):
        q = EvalQuestion("Q1", "text", True, ("NCT1",), "basis")
        problems = validate_questions([q, q], {"NCT1"})
        assert any("duplicate" in p for p in problems)

    def test_flags_answerable_with_no_ground_truth(self):
        q = EvalQuestion("Q1", "text", True, (), "basis")
        problems = validate_questions([q], set())
        assert any("expect_answerable=True" in p for p in problems)

    def test_flags_trap_with_ground_truth(self):
        q = EvalQuestion("A1", "text", False, ("NCT1",), "basis")
        problems = validate_questions([q], {"NCT1"})
        assert any("expect_answerable=False" in p for p in problems)

    def test_flags_unknown_identifier(self):
        q = EvalQuestion("Q1", "text", True, ("NCT_UNKNOWN",), "basis")
        problems = validate_questions([q], {"NCT1"})
        assert any("unknown identifier" in p for p in problems)

    def test_flags_empty_question_text(self):
        q = EvalQuestion("Q1", "   ", True, ("NCT1",), "basis")
        problems = validate_questions([q], {"NCT1"})
        assert any("empty" in p for p in problems)

    def test_flags_wrong_total_counts(self):
        q = EvalQuestion("Q1", "text", True, ("NCT1",), "basis")
        problems = validate_questions([q], {"NCT1"})
        assert any("expected 20 questions" in p for p in problems)

    def test_no_problems_for_a_well_formed_minimal_set(self):
        answerable = [
            EvalQuestion(f"Q{i}", "text", True, ("NCT1",), "basis") for i in range(15)
        ]
        traps = [EvalQuestion(f"A{i}", "text", False, (), "basis") for i in range(5)]
        problems = validate_questions(answerable + traps, {"NCT1"})
        assert problems == []
