/**
 * TypeScript mirrors of the backend's Pydantic response models
 * (backend/app/schemas/retrieval.py, backend/app/schemas/generation.py).
 * Kept in one place so a backend field rename surfaces as a single
 * diff here rather than scattered inline shapes across pages.
 */

export type SourceType = "trial" | "publication";

export interface RetrievalResult {
  chunk_id: number;
  document_id: number;
  source_type: SourceType;
  source_identifier: string;
  source_url: string;
  title: string;
  excerpt: string;
  score: number;
  matched_by: string[];
}

export type RetrievalMode = "hybrid" | "fulltext" | "dense";

export interface RetrievalResponse {
  query: string;
  mode: RetrievalMode;
  results: RetrievalResult[];
}

export interface Citation {
  index: number;
  chunk_id: number;
  document_id: number;
  source_type: SourceType;
  source_identifier: string;
  source_url: string;
  title: string;
  excerpt: string;
}

export type AnswerStatus = "answered" | "insufficient_evidence" | "validation_failed";

export interface AnswerResponse {
  status: AnswerStatus;
  query: string;
  answer: string | null;
  citations: Citation[];
  warnings: string[];
}
