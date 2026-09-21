"""One-off sandbox verification: a hybrid-EQUIVALENT Recall@5/MRR run.

Builds on fulltext_eval_check.py's real fulltext-only result (which
found ~0 recall, root-caused to plainto_tsquery's AND semantics — see
docs/evaluation-report.md). This script adds the dense half using the
REAL production code (app.retrieval.embeddings.HashingEmbeddingProvider,
the same class app/retrieval/dense.py's SQL and app/retrieval/hybrid.py
call in production) and the REAL app.retrieval.fusion.reciprocal_rank_fusion,
executed directly in Python:

- Dense ranking needs pgvector's `<=>` cosine-distance SQL operator to
  run inside Postgres, which this sandbox's Postgres install cannot do
  (the `vector` extension's control file is absent — see
  docs/known-limitations.md). But cosine similarity is just arithmetic
  over the *same* embedding vectors HashingEmbeddingProvider.embed()
  produces — computing "1 - cosine_distance" in Python, over vectors
  from the exact real code, gives the mathematically identical ranking
  pgvector's `<=>` operator would produce for those same vectors. That's
  a faithful re-execution of dense_search's algorithm, not a
  reimplementation of different logic and not a fabricated number.
- Fulltext ranking reuses the exact real ts_rank/plainto_tsquery SQL
  against a real Postgres (same as fulltext_eval_check.py).
- Fusion calls app.retrieval.fusion.reciprocal_rank_fusion directly —
  the actual RRF implementation app/retrieval/hybrid.py calls.
- Recall@5/MRR call app.evaluation.metrics directly — the actual metric
  functions, already unit-tested (tests/test_evaluation_metrics.py).

This is explicitly labeled "hybrid-equivalent," not "hybrid," in every
report that cites it: it was not executed through the real dense_search
SQL path (no pgvector involved at any point), so it does not verify that
SQL/pgvector integration itself — only the retrieval *algorithm* end to
end. See docs/evaluation-report.md for exactly how this is reported.
"""

import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, "/home/claude/trial-lens-lite/backend")

from app.evaluation.metrics import mean_recall_at_k, mean_reciprocal_rank, recall_at_k, reciprocal_rank
from app.ingestion.normalize import normalize_publication, normalize_trial
from app.retrieval.embeddings import HashingEmbeddingProvider
from app.retrieval.fusion import reciprocal_rank_fusion

REPO = Path("/home/claude/trial-lens-lite")
DB_NAME = "triallens_hybrid_eq_check"


def run_psql(sql: str) -> str:
    args = ["sudo", "-u", "postgres", "psql", "-d", DB_NAME, "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t"]
    result = subprocess.run(args, input=sql, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed:\n{result.stderr}")
    return result.stdout


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def main() -> None:
    subprocess.run(["sudo", "-u", "postgres", "dropdb", "--if-exists", DB_NAME], check=True)
    subprocess.run(["sudo", "-u", "postgres", "createdb", DB_NAME], check=True)
    ddl = """
    CREATE TABLE documents (id SERIAL PRIMARY KEY, source_identifier VARCHAR(20) NOT NULL);
    CREATE TABLE chunks (
        id SERIAL PRIMARY KEY,
        document_id INTEGER NOT NULL REFERENCES documents(id),
        text TEXT NOT NULL,
        text_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    );
    """
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", DB_NAME, "-v", "ON_ERROR_STOP=1"],
        input=ddl, text=True, check=True, capture_output=True,
    )

    ctgov = json.loads((REPO / "data/evaluation/fixtures_ctgov.json").read_text())
    trials = [normalize_trial(s) for s in ctgov["studies"]]
    pubmed_xml = (REPO / "data/evaluation/fixtures_pubmed.xml").read_text()
    root = ET.fromstring(pubmed_xml)
    publications = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        article_xml = ET.tostring(article, encoding="unicode")
        publications.append(normalize_publication(pmid, article_xml, article))

    rows = [(t.nct_id, t.document_text) for t in trials] + [(p.pmid, p.document_text) for p in publications]

    insert_stmts = [
        f"WITH d AS (INSERT INTO documents (source_identifier) VALUES ({sql_quote(sid)}) RETURNING id) "
        f"INSERT INTO chunks (document_id, text) SELECT id, {sql_quote(text)} FROM d "
        f"RETURNING {sql_quote(sid)}, id;"
        for sid, text in rows
    ]
    insert_out = run_psql("\n".join(insert_stmts))
    chunk_id_to_source = {}
    chunk_id_to_text = {}
    text_by_sid = dict(rows)
    for line in insert_out.strip().splitlines():
        if "\t" not in line:
            continue
        sid, chunk_id = line.split("\t")
        chunk_id_to_source[int(chunk_id)] = sid
        chunk_id_to_text[int(chunk_id)] = text_by_sid[sid]

    print(f"Seeded {len(chunk_id_to_source)} document/chunk rows.")

    # Real embedding provider, real code, dimension matching production default.
    provider = HashingEmbeddingProvider(dimension=256)
    chunk_ids_sorted = sorted(chunk_id_to_text)
    chunk_embeddings = dict(
        zip(chunk_ids_sorted, provider.embed([chunk_id_to_text[cid] for cid in chunk_ids_sorted]))
    )

    questions = json.loads((REPO / "data/evaluation/questions.json").read_text())["questions"]
    answerable = [q for q in questions if q["expect_answerable"]]

    pairs_recall = []
    pairs_mrr = []
    per_question = []

    for q in answerable:
        # Real fulltext ranking (same SQL as app/retrieval/fulltext.py).
        query_sql = f"""
        SELECT id, ts_rank(text_tsv, plainto_tsquery('english', {sql_quote(q['question'])})) AS score
        FROM chunks
        WHERE text_tsv @@ plainto_tsquery('english', {sql_quote(q['question'])})
        ORDER BY score DESC
        LIMIT 40;
        """
        out = run_psql(query_sql)
        fulltext_chunk_ids = [int(line.split("\t")[0]) for line in out.strip().splitlines() if line.strip()]

        # Dense ranking: real embedding provider, cosine similarity computed
        # in Python (mathematically identical to pgvector's 1 - (a <=> b)).
        [query_embedding] = provider.embed([q["question"]])
        dense_ranked = sorted(
            chunk_ids_sorted,
            key=lambda cid: cosine_similarity(query_embedding, chunk_embeddings[cid]),
            reverse=True,
        )[:40]

        # Real RRF fusion (app.retrieval.fusion.reciprocal_rank_fusion).
        fused = reciprocal_rank_fusion([fulltext_chunk_ids, dense_ranked], k=60)
        top_chunk_ids = [item.item_id for item in fused][:10]
        retrieved_source_ids = []
        seen = set()
        for cid in top_chunk_ids:
            sid = chunk_id_to_source[cid]
            if sid not in seen:
                seen.add(sid)
                retrieved_source_ids.append(sid)

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
    print(f"Mean Recall@5 (hybrid-EQUIVALENT: real fulltext SQL + real hashing-embedding cosine similarity computed in Python + real RRF, n={len(answerable)}): {mean_r5:.4f}")
    print(f"MRR (hybrid-equivalent, n={len(answerable)}): {mrr:.4f}")

    subprocess.run(["sudo", "-u", "postgres", "dropdb", DB_NAME], check=True)
    print(f"\nDropped disposable database {DB_NAME}.")


if __name__ == "__main__":
    main()
