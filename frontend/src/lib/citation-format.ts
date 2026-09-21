import type { SourceType } from "./api-types";

/** Trials show their NCT number as-is; publications show "PMID 12345678". */
export function formatSourceLabel(sourceType: SourceType, sourceIdentifier: string): string {
  return sourceType === "publication" ? `PMID ${sourceIdentifier}` : sourceIdentifier;
}

export function formatSourceTypeName(sourceType: SourceType): string {
  return sourceType === "publication" ? "Publication" : "Registered trial";
}

/**
 * Reciprocal-rank-fusion scores aren't a 0-1 relevance probability (see
 * backend/app/retrieval/fusion.py) — round for display without
 * implying more precision, or meaning, than the number actually
 * carries.
 */
export function formatScore(score: number): string {
  return score.toFixed(4);
}

/** Truncate on a word boundary rather than mid-word, appending an ellipsis. */
export function truncateExcerpt(text: string, maxLength: number): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;

  const cut = trimmed.slice(0, maxLength);
  const lastSpace = cut.lastIndexOf(" ");
  const safeCut = lastSpace > 0 ? cut.slice(0, lastSpace) : cut;
  return `${safeCut.trimEnd()}…`;
}

export interface AnswerSegment {
  text: string;
  /** null for a plain-text segment; the parsed indices for a "[1]"/"[1, 3]" marker segment. */
  citationIndices: number[] | null;
}

const CITATION_PATTERN = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/**
 * Splits a generated answer on its "[n]"/"[n, m]" citation markers so a
 * page can render the plain-text segments and citation markers
 * differently (e.g. the marker as a small link to its CitationCard)
 * instead of showing the raw bracket syntax verbatim. Mirrors the
 * citation-marker regex in backend/app/generation/citations.py.
 */
export function splitAnswerIntoSegments(answer: string): AnswerSegment[] {
  const segments: AnswerSegment[] = [];
  let lastIndex = 0;

  for (const match of answer.matchAll(CITATION_PATTERN)) {
    const matchIndex = match.index ?? 0;
    if (matchIndex > lastIndex) {
      segments.push({ text: answer.slice(lastIndex, matchIndex), citationIndices: null });
    }
    const indices = match[1].split(",").map((piece) => Number(piece.trim()));
    segments.push({ text: match[0], citationIndices: indices });
    lastIndex = matchIndex + match[0].length;
  }

  if (lastIndex < answer.length) {
    segments.push({ text: answer.slice(lastIndex), citationIndices: null });
  }

  return segments;
}
