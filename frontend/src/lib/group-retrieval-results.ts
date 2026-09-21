import type { RetrievalResult, SourceType } from "./api-types";

export interface DocumentExcerpt {
  chunkId: number;
  excerpt: string;
  score: number;
}

export interface DocumentGroup {
  sourceType: SourceType;
  sourceIdentifier: string;
  sourceUrl: string;
  title: string;
  bestScore: number;
  matchedBy: string[];
  excerpts: DocumentExcerpt[];
}

/**
 * The backend has no dedicated trial/publication search endpoint (see
 * docs/phase-5-notes.md) — the trial and publication search pages are
 * built on top of the chunk-level `GET /api/v1/retrieve` endpoint
 * instead, grouping its per-chunk hits back into one card per source
 * document. Pure and network-free, so it's directly unit-testable.
 */
export function groupBySourceDocument(
  results: RetrievalResult[],
  sourceType: SourceType
): DocumentGroup[] {
  const groups = new Map<string, DocumentGroup>();

  for (const result of results) {
    if (result.source_type !== sourceType) continue;

    const excerpt: DocumentExcerpt = {
      chunkId: result.chunk_id,
      excerpt: result.excerpt,
      score: result.score,
    };

    const existing = groups.get(result.source_identifier);
    if (!existing) {
      groups.set(result.source_identifier, {
        sourceType: result.source_type,
        sourceIdentifier: result.source_identifier,
        sourceUrl: result.source_url,
        title: result.title,
        bestScore: result.score,
        matchedBy: [...result.matched_by],
        excerpts: [excerpt],
      });
      continue;
    }

    existing.excerpts.push(excerpt);
    existing.bestScore = Math.max(existing.bestScore, result.score);
    for (const matcher of result.matched_by) {
      if (!existing.matchedBy.includes(matcher)) existing.matchedBy.push(matcher);
    }
  }

  const groupList = Array.from(groups.values());
  for (const group of groupList) {
    group.excerpts.sort((a, b) => b.score - a.score);
  }
  groupList.sort((a, b) => b.bestScore - a.bestScore);
  return groupList;
}
