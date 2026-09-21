"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { retrieveEvidence } from "@/lib/api";
import { groupBySourceDocument, type DocumentGroup } from "@/lib/group-retrieval-results";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { DocumentResultCard } from "@/components/DocumentResultCard";

/**
 * There's no dedicated "list/search trials" backend endpoint (see
 * docs/phase-5-notes.md) — this searches the chunk-level
 * GET /api/v1/retrieve endpoint and groups the hits tagged
 * source_type: "trial" back into one card per trial.
 */
export default function TrialSearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [groups, setGroups] = useState<DocumentGroup[]>([]);
  const [selected, setSelected] = useState<string[]>([]);

  async function runSearch(q: string) {
    if (!q.trim()) return;
    setStatus("loading");
    setError(null);

    const result = await retrieveEvidence(q, { mode: "hybrid", k: 30 });
    if (!result.ok) {
      setError(result.error);
      setStatus("error");
      return;
    }

    setGroups(groupBySourceDocument(result.data.results, "trial"));
    setStatus("done");
  }

  function toggleSelected(nctId: string) {
    setSelected((current) => {
      if (current.includes(nctId)) return current.filter((id) => id !== nctId);
      if (current.length >= 2) return current;
      return [...current, nctId];
    });
  }

  function goToComparison() {
    if (selected.length !== 2) return;
    router.push(`/compare?a=${encodeURIComponent(selected[0])}&b=${encodeURIComponent(selected[1])}`);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trial search</h1>
        <p className="mt-1 text-sm text-slate-600">
          Searches ingested ClinicalTrials.gov records by full text and meaning combined
          (reciprocal-rank fusion over full-text and dense retrieval).
        </p>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void runSearch(query);
        }}
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. pembrolizumab overall survival"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={status === "loading" || !query.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Search
        </button>
      </form>

      {selected.length > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-900">
          <span>
            {selected.length === 1
              ? "1 trial selected — pick one more to compare."
              : `2 trials selected: ${selected.join(", ")}`}
          </span>
          <button
            type="button"
            onClick={goToComparison}
            disabled={selected.length !== 2}
            className="rounded-md bg-sky-700 px-3 py-1.5 font-medium text-white disabled:opacity-40"
          >
            Compare selected
          </button>
        </div>
      )}

      {status === "loading" && <LoadingState label="Searching trials…" />}
      {status === "error" && error && <ErrorState message={error} onRetry={() => void runSearch(query)} />}

      {status === "done" && groups.length === 0 && (
        <p className="text-sm text-slate-500">No ingested trials matched that search.</p>
      )}

      {status === "done" && groups.length > 0 && (
        <ul className="flex flex-col gap-3">
          {groups.map((group) => (
            <li key={group.sourceIdentifier}>
              <DocumentResultCard
                group={group}
                action={
                  <label className="flex items-center gap-2 text-sm text-slate-600">
                    <input
                      type="checkbox"
                      checked={selected.includes(group.sourceIdentifier)}
                      onChange={() => toggleSelected(group.sourceIdentifier)}
                      disabled={!selected.includes(group.sourceIdentifier) && selected.length >= 2}
                    />
                    Select for comparison
                  </label>
                }
              />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
