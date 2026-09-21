"""Shared filesystem paths for the Phase 6 evaluation corpus.

Deliberately its own tiny, dependency-free module (no sqlalchemy, no
anything beyond ``pathlib``) so that pure code needing only *where the
fixture files are* — like ``app.evaluation.dataset`` and
``tests/test_evaluation_dataset.py`` — never has to import
``app.evaluation.seed_fixtures`` (which pulls in ``sqlalchemy`` via
``app.ingestion.ingest_clinicaltrials``/``ingest_pubmed``) just to read a
path constant. That split is what keeps the dataset-validation tests
directly executable in an environment with no third-party packages at
all, the same dependency-free-core pattern used throughout this project.
"""

from __future__ import annotations

from pathlib import Path

# backend/app/evaluation/paths.py -> app -> backend -> trial-lens-lite
_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_QUESTIONS_PATH = _REPO_ROOT / "data" / "evaluation" / "questions.json"
DEFAULT_CTGOV_FIXTURES = _REPO_ROOT / "data" / "evaluation" / "fixtures_ctgov.json"
DEFAULT_PUBMED_FIXTURES = _REPO_ROOT / "data" / "evaluation" / "fixtures_pubmed.xml"
