import { describe, expect, it } from "vitest";
import { groupBySourceDocument } from "../group-retrieval-results";
import type { RetrievalResult } from "../api-types";

function result(overrides: Partial<RetrievalResult>): RetrievalResult {
  return {
    chunk_id: 1,
    document_id: 1,
    source_type: "trial",
    source_identifier: "NCT00000001",
    source_url: "https://clinicaltrials.gov/study/NCT00000001",
    title: "A test trial",
    excerpt: "excerpt text",
    score: 0.5,
    matched_by: ["fulltext"],
    ...overrides,
  };
}

describe("groupBySourceDocument", () => {
  it("filters out results that don't match the requested source type", () => {
    const groups = groupBySourceDocument(
      [result({ source_type: "trial" }), result({ source_type: "publication", source_identifier: "111" })],
      "publication"
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].sourceIdentifier).toBe("111");
  });

  it("groups multiple chunk hits from the same document into one card", () => {
    const groups = groupBySourceDocument(
      [
        result({ chunk_id: 1, excerpt: "first excerpt", score: 0.3 }),
        result({ chunk_id: 2, excerpt: "second excerpt", score: 0.7 }),
      ],
      "trial"
    );

    expect(groups).toHaveLength(1);
    expect(groups[0].excerpts).toHaveLength(2);
    expect(groups[0].bestScore).toBe(0.7);
  });

  it("sorts excerpts within a group by score, best first", () => {
    const groups = groupBySourceDocument(
      [
        result({ chunk_id: 1, excerpt: "low", score: 0.2 }),
        result({ chunk_id: 2, excerpt: "high", score: 0.9 }),
        result({ chunk_id: 3, excerpt: "mid", score: 0.5 }),
      ],
      "trial"
    );

    expect(groups[0].excerpts.map((e) => e.excerpt)).toEqual(["high", "mid", "low"]);
  });

  it("sorts groups by best score, best first", () => {
    const groups = groupBySourceDocument(
      [
        result({ source_identifier: "NCT1", score: 0.1 }),
        result({ source_identifier: "NCT2", score: 0.9 }),
      ],
      "trial"
    );

    expect(groups.map((g) => g.sourceIdentifier)).toEqual(["NCT2", "NCT1"]);
  });

  it("merges matched_by labels across a document's chunks without duplicates", () => {
    const groups = groupBySourceDocument(
      [
        result({ chunk_id: 1, matched_by: ["fulltext"] }),
        result({ chunk_id: 2, matched_by: ["dense", "fulltext"] }),
      ],
      "trial"
    );

    expect(groups[0].matchedBy.sort()).toEqual(["dense", "fulltext"]);
  });

  it("returns an empty list when there are no results for that source type", () => {
    expect(groupBySourceDocument([], "trial")).toEqual([]);
    expect(groupBySourceDocument([result({ source_type: "publication" })], "trial")).toEqual([]);
  });
});
