/**
 * Backend API client.
 *
 * The browser calls the FastAPI backend directly (no Next.js API
 * routes/proxying — see next.config.mjs) using `NEXT_PUBLIC_API_URL`.
 * Every call below returns an `ApiResult` and never throws; the actual
 * status/body parsing is pure and lives in api-result.ts so it can be
 * unit-tested without a network stack (see
 * src/lib/__tests__/api-result.test.ts).
 */

import { parseApiResponse, type ApiResult } from "./api-result";
import type { AnswerResponse, RetrievalMode, RetrievalResponse } from "./api-types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BackendStatus = { ok: boolean; detail: string };

/**
 * Calls the backend's /ready endpoint (DB + app check). Never throws:
 * network/backend failures are surfaced as `{ ok: false }` so the
 * homepage can render a status badge either way.
 */
export async function getBackendStatus(): Promise<BackendStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/ready`, { cache: "no-store" });

    if (!response.ok) {
      return { ok: false, detail: `backend responded with ${response.status}` };
    }

    const data = (await response.json()) as { status?: string };
    return { ok: data.status === "ready", detail: data.status ?? "unknown" };
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    return { ok: false, detail: `unreachable: ${message}` };
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const bodyText = await response.text();
    return parseApiResponse<T>(response.status, response.ok, bodyText);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown network error.";
    return { ok: false, error: `Couldn't reach the backend: ${message}`, status: 0 };
  }
}

/** GET /api/v1/retrieve — chunk-level full-text/dense/hybrid search (Phase 3). */
export function retrieveEvidence(
  query: string,
  options: { mode?: RetrievalMode; k?: number } = {}
): Promise<ApiResult<RetrievalResponse>> {
  const params = new URLSearchParams({ q: query });
  if (options.mode) params.set("mode", options.mode);
  if (options.k) params.set("k", String(options.k));
  return apiFetch<RetrievalResponse>(`/api/v1/retrieve?${params.toString()}`);
}

/**
 * POST /api/v1/ask — grounded, cited Q&A (Phase 4). Each call is
 * independent: the backend has no conversation memory, so earlier
 * questions in an "Evidence chat" session are not sent as context.
 */
export function askQuestion(question: string, topK?: number): Promise<ApiResult<AnswerResponse>> {
  return apiFetch<AnswerResponse>(`/api/v1/ask`, {
    method: "POST",
    body: JSON.stringify({ question, top_k: topK ?? null }),
  });
}

/** POST /api/v1/compare — grounded trial-vs-trial comparison (Phase 4). */
export function compareTrials(
  nctIdA: string,
  nctIdB: string,
  question?: string
): Promise<ApiResult<AnswerResponse>> {
  return apiFetch<AnswerResponse>(`/api/v1/compare`, {
    method: "POST",
    body: JSON.stringify({ nct_id_a: nctIdA, nct_id_b: nctIdB, question: question || null }),
  });
}

export type { ApiResult } from "./api-result";
