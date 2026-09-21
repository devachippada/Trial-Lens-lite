import { describe, expect, it } from "vitest";
import {
  formatSourceLabel,
  formatSourceTypeName,
  splitAnswerIntoSegments,
  truncateExcerpt,
} from "../citation-format";

describe("formatSourceLabel", () => {
  it("shows a trial's NCT id as-is", () => {
    expect(formatSourceLabel("trial", "NCT00000001")).toBe("NCT00000001");
  });

  it("prefixes a publication's identifier with PMID", () => {
    expect(formatSourceLabel("publication", "12345678")).toBe("PMID 12345678");
  });
});

describe("formatSourceTypeName", () => {
  it("labels trials and publications distinctly", () => {
    expect(formatSourceTypeName("trial")).toBe("Registered trial");
    expect(formatSourceTypeName("publication")).toBe("Publication");
  });
});

describe("truncateExcerpt", () => {
  it("leaves short text unchanged", () => {
    expect(truncateExcerpt("short text", 100)).toBe("short text");
  });

  it("truncates on a word boundary and appends an ellipsis", () => {
    const text = "The quick brown fox jumps over the lazy dog";
    const truncated = truncateExcerpt(text, 19);
    expect(truncated).toBe("The quick brown…");
    expect(truncated.length).toBeLessThanOrEqual(20);
  });

  it("trims surrounding whitespace before measuring length", () => {
    expect(truncateExcerpt("   short text   ", 100)).toBe("short text");
  });
});

describe("splitAnswerIntoSegments", () => {
  it("returns a single plain-text segment when there are no citations", () => {
    expect(splitAnswerIntoSegments("No citations here.")).toEqual([
      { text: "No citations here.", citationIndices: null },
    ]);
  });

  it("splits text around a single citation marker", () => {
    const segments = splitAnswerIntoSegments("Overall survival improved [1].");
    expect(segments).toEqual([
      { text: "Overall survival improved ", citationIndices: null },
      { text: "[1]", citationIndices: [1] },
      { text: ".", citationIndices: null },
    ]);
  });

  it("parses a comma-grouped citation into multiple indices", () => {
    const segments = splitAnswerIntoSegments("Consistent across arms [1, 3].");
    const marker = segments.find((s) => s.citationIndices !== null);
    expect(marker?.citationIndices).toEqual([1, 3]);
  });

  it("handles a citation at the very start of the answer", () => {
    const segments = splitAnswerIntoSegments("[1] Overall survival improved.");
    expect(segments[0]).toEqual({ text: "[1]", citationIndices: [1] });
  });

  it("handles adjacent citation markers with no text between them", () => {
    const segments = splitAnswerIntoSegments("Supported by two sources[1][2].");
    const markers = segments.filter((s) => s.citationIndices !== null);
    expect(markers.map((m) => m.citationIndices)).toEqual([[1], [2]]);
  });

  it("returns an empty array for an empty answer", () => {
    expect(splitAnswerIntoSegments("")).toEqual([]);
  });
});
