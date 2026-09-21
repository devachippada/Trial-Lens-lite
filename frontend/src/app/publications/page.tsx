"use client";

import { useState } from "react";
import { retrieveEvidence } from "@/lib/api";
import { groupBySourceDocument, type DocumentGroup } from "@/lib/group-retrieval-results";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { DocumentResultCard } from "@/components/DocumentResultCard";

/**
 * Same approach as the trial search page (see app/trials/page.tsx):
 * there's no dedicated publication-search endpoint, so this searches
 * GET /api/v1/retrieve and groups the hits tagged
 * source_type: "publication" into one card per publication.
 */
export default function PublicationSearchPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [groups, setGroups] = useState<DocumentGroup[]>([]);

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

    setGroups(groupBySourceDocument(result.data.results, "publication"));
    setStatus("done");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Publication search</h1>
        <p className="mt-1 text-sm text-slate-600">
          Searches ingested PubMed publications by full text and meaning combined
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
          placeholder="e.g. adverse events pembrolizumab"
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

      {status === "loading" && <LoadingState label="Searching publications…" />}
      {status === "error" && error && <ErrorState message={error} onRetry={() => void runSearch(query)} />}

      {status === "done" && groups.length === 0 && (
        <p className="text-sm text-slate-500">No ingested publications matched that search.</p>
      )}

      {status === "done" && groups.length > 0 && (
        <ul className="flex flex-col gap-3">
          {groups.map((group) => (
            <li key={group.sourceIdentifier}>
              <DocumentResultCard group={group} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
