"""One-off sandbox verification: a REAL fulltext-only Recall@5/MRR run.

Why this exists: neither sqlalchemy nor psycopg/psycopg2 are installed in
this sandbox (see docs/phase-2-notes.md onward), so app/retrieval/*.py
and app/evaluation/run_eval.py cannot actually be executed here even
though a real Postgres 16 server IS running. This script re-implements
just enough of the fulltext path by hand — using the exact same SQL as
app/retrieval/fulltext.py's fulltext_search (ts_rank / plainto_tsquery)
and app/evaluation/metrics.py's real recall_at_k/reciprocal_rank
functions (imported directly, not reimplemented) — to get one genuinely
executed, non-fabricated data point: does the retrieval+metrics math
actually work against a real database, for the real 15-question
evaluation set, on the fulltext half of hybrid retrieval.

This is NOT a substitute for running app/evaluation/run_eval.py for
real: it skips dense/hybrid retrieval entirely (pgvector's extension
control file is absent from this Postgres install — a hard environment
gap, not a code defect) and it does not call Claude, so it says nothing
about citation correctness/completeness or abstention accuracy. See
docs/evaluation-report.md for how this result is reported and
docs/phase-6-notes.md for the full list of what still needs the user's
own environment.

Uses a disposable database (created and dropped by this script) so
nothing here touches the `triallens` database other phases' tests use.
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, "/home/claude/trial-lens-lite/backend")

from app.evaluation.metrics import mean_recall_at_k, mean_reciprocal_rank, recall_at_k, reciprocal_rank
from app.ingestion.normalize import normalize_publication, normalize_trial

REPO = Path("/home/claude/trial-lens-lite")
DB_NAME = "triallens_eval_check"


def run_psql(sql: str, tuples_only: bool = True) -> str:
    args = ["sudo", "-u", "postgres", "psql", "-d", DB_NAME, "-v", "ON_ERROR_STOP=1"]
    if tuples_only:
        args += ["-t", "-A", "-F", "\t"]
    result = subprocess.run(args, input=sql, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed:\n{result.stderr}")
    return result.stdout


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    # 1. Fresh disposable database, run as the postgres superuser (no
    # trust-auth password needed locally).
    subprocess.run(
        ["sudo", "-u", "postgres", "dropdb", "--if-exists", DB_NAME], check=True
    )
    subprocess.run(["sudo", "-u", "postgres", "createdb", DB_NAME], check=True)

    ddl = """
    CREATE TABLE documents (
        id SERIAL PRIMARY KEY,
        source_identifier VARCHAR(20) NOT NULL
    );
    CREATE TABLE chunks (
        id SERIAL PRIMARY KEY,
        document_id INTEGER NOT NULL REFERENCES documents(id),
        text TEXT NOT NULL,
        text_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    );
    CREATE INDEX chunks_text_tsv_idx ON chunks USING GIN (text_tsv);
    """
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", DB_NAME, "-v", "ON_ERROR_STOP=1"],
        input=ddl, text=True, check=True, capture_output=True,
    )

    # 2. Normalize the real fixtures with the real normalize_trial/
    # normalize_publication functions (identical to what seed_fixtures.py
    # does), then insert one document+chunk row per source, exactly as
    # app/retrieval/index_documents.py would after chunk_text (already
    # confirmed separately to produce exactly one chunk per document).
    ctgov = json.loads((REPO / "data/evaluation/fixtures_ctgov.json").read_text())
    trials = [normalize_trial(s) for s in ctgov["studies"]]

    pubmed_xml = (REPO / "data/evaluation/fixtures_pubmed.xml").read_text()
    root = ET.fromstring(pubmed_xml)
    publications = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        article_xml = ET.tostring(article, encoding="unicode")
        publications.append(normalize_publication(pmid, article_xml, article))

    insert_sql_parts = []
    source_identifier_by_chunk_alias = {}  # alias -> source_identifier, filled after insert via RETURNING
    rows = []
    for t in trials:
        rows.append((t.nct_id, t.document_text))
    for p in publications:
        rows.append((p.pmid, p.document_text))

    # Insert and capture (source_identifier, chunk_id) pairs via RETURNING.
    insert_stmts = []
    for source_identifier, doc_text in rows:
        # The RETURNING clause deliberately returns the *literal*
        # source_identifier (known here in Python), not a correlated
        # subquery back into `documents` — a data-modifying CTE and its
        # outer statement share one snapshot, so a subquery in RETURNING
        # can't see the CTE's own just-inserted row.
        insert_stmts.append(
            f"WITH d AS (INSERT INTO documents (source_identifier) VALUES ({sql_quote(source_identifier)}) RETURNING id) "
            f"INSERT INTO chunks (document_id, text) SELECT id, {sql_quote(doc_text)} FROM d "
            f"RETURNING {sql_quote(source_identifier)}, id;"
        )
    insert_out = run_psql("\n".join(insert_stmts))
    chunk_id_to_source = {}
    for line in insert_out.strip().splitlines():
        # psql -t still prints each statement's "INSERT 0 1" command tag
        # interleaved with RETURNING data lines when multiple statements
        # are batched — those tags have no tab, so skip them.
        if "\t" not in line:
            continue
        source_identifier, chunk_id = line.split("\t")
        chunk_id_to_source[int(chunk_id)] = source_identifier

    print(f"Seeded {len(chunk_id_to_source)} document/chunk rows into {DB_NAME}: {sorted(chunk_id_to_source.values())}")

    # 3. Run the exact fulltext_search SQL for each of the 15 answerable
    # questions, at limit=5 (Recall@5), and compute real metrics.
    questions = json.loads((REPO / "data/evaluation/questions.json").read_text())["questions"]
    answerable = [q for q in questions if q["expect_answerable"]]

    pairs_recall = []
    pairs_mrr = []
    per_question = []
    for q in answerable:
        query_sql = f"""
        SELECT id, ts_rank(text_tsv, plainto_tsquery('english', {sql_quote(q['question'])})) AS score
        FROM chunks
        WHERE text_tsv @@ plainto_tsquery('english', {sql_quote(q['question'])})
        ORDER BY score DESC
        LIMIT 5;
        """
        out = run_psql(query_sql)
        retrieved_chunk_ids = [int(line.split("\t")[0]) for line in out.strip().splitlines() if line.strip()]
        retrieved_source_ids = [chunk_id_to_source[cid] for cid in retrieved_chunk_ids]
        relevant = set(q["relevant_source_identifiers"])

        r5 = recall_at_k(retrieved_source_ids, relevant, k=5)
        rr = reciprocal_rank(retrieved_source_ids, relevant)
        pairs_recall.append((retrieved_source_ids, relevant))
        pairs_mrr.append((retrieved_source_ids, relevant))
        per_question.append((q["id"], retrieved_source_ids, sorted(relevant), r5, rr))

    print()
    print(f"{'ID':4} {'Recall@5':9} {'RR':6}  retrieved -> relevant")
    for qid, retrieved, relevant, r5, rr in per_question:
        print(f"{qid:4} {r5:<9.2f} {rr:<6.2f} {retrieved} -> {relevant}")

    mean_r5 = mean_recall_at_k(pairs_recall, k=5)
    mrr = mean_reciprocal_rank(pairs_mrr)
    print()
    print(f"Mean Recall@5 (fulltext-only, real Postgres, n={len(answerable)}): {mean_r5:.4f}")
    print(f"MRR (fulltext-only, real Postgres, n={len(answerable)}): {mrr:.4f}")

    # 4. Clean up.
    subprocess.run(["sudo", "-u", "postgres", "dropdb", DB_NAME], check=True)
    print(f"\nDropped disposable database {DB_NAME}.")


if __name__ == "__main__":
    main()
