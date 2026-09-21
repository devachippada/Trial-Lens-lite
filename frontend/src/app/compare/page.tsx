"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { compareTrials } from "@/lib/api";
import { validateComparisonInput } from "@/lib/validation";
import type { AnswerResponse, Citation } from "@/lib/api-types";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { AnswerStatusNotice } from "@/components/AnswerStatusNotice";
import { CitedAnswer } from "@/components/CitedAnswer";
import { CitationCard } from "@/components/CitationCard";

type RequestState = "idle" | "loading" | "error" | "done";

function citationsForTrial(citations: Citation[], nctId: string): Citation[] {
  return citations.filter((c) => c.source_identifier.toUpperCase() === nctId.toUpperCase());
}

function TrialComparisonForm() {
  const searchParams = useSearchParams();
  const [nctIdA, setNctIdA] = useState(searchParams.get("a") ?? "");
  const [nctIdB, setNctIdB] = useState(searchParams.get("b") ?? "");
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<RequestState>("idle");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);

  async function runComparison() {
    const problem = validateComparisonInput(nctIdA, nctIdB);
    setValidationError(problem);
    if (problem) return;

    setState("loading");
    setApiError(null);

    const result = await compareTrials(nctIdA.trim(), nctIdB.trim(), question.trim() || undefined);
    if (!result.ok) {
      setApiError(result.error);
      setState("error");
      return;
    }

    setAnswer(result.data);
    setState("done");
  }

  const citationsA = answer ? citationsForTrial(answer.citations, nctIdA.trim()) : [];
  const citationsB = answer ? citationsForTrial(answer.citations, nctIdB.trim()) : [];
  const otherCitations = answer
    ? answer.citations.filter((c) => !citationsA.includes(c) && !citationsB.includes(c))
    : [];

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compare trials</h1>
        <p className="mt-1 text-sm text-slate-600">
          Compares two ingested, registered trials using only their own retrieved text — never
          outside knowledge, and never mixing one trial&rsquo;s data into the other&rsquo;s.
        </p>
      </div>

      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void runComparison();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Trial A (NCT number)</span>
            <input
              type="text"
              value={nctIdA}
              onChange={(e) => setNctIdA(e.target.value)}
              placeholder="NCT00000001"
              className="rounded-md border border-slate-300 px-3 py-2 focus:border-slate-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-slate-700">Trial B (NCT number)</span>
            <input
              type="text"
              value={nctIdB}
              onChange={(e) => setNctIdB(e.target.value)}
              placeholder="NCT00000002"
              className="rounded-md border border-slate-300 px-3 py-2 focus:border-slate-500 focus:outline-none"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700">Focus the comparison on (optional)</span>
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Defaults to design, population, and primary endpoints/outcomes"
            className="rounded-md border border-slate-300 px-3 py-2 focus:border-slate-500 focus:outline-none"
          />
        </label>

        {validationError && <p className="text-sm text-red-700">{validationError}</p>}

        <button
          type="submit"
          disabled={state === "loading"}
          className="self-start rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Compare
        </button>
      </form>

      {state === "loading" && <LoadingState label="Gathering each trial's evidence and asking Claude…" />}
      {state === "error" && apiError && <ErrorState message={apiError} onRetry={() => void runComparison()} />}

      {state === "done" && answer && (
        <div className="flex flex-col gap-4">
          <AnswerStatusNotice status={answer.status} warnings={answer.warnings} />

          {answer.status === "answered" && answer.answer && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <CitedAnswer text={answer.answer} />
            </div>
          )}

          {(citationsA.length > 0 || citationsB.length > 0) && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Trial A evidence ({nctIdA.trim()})
                </p>
                {citationsA.length === 0 && <p className="text-sm text-slate-500">No citations for this trial.</p>}
                {citationsA.map((citation) => (
                  <CitationCard key={citation.index} citation={citation} />
                ))}
              </div>
              <div className="flex flex-col gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Trial B evidence ({nctIdB.trim()})
                </p>
                {citationsB.length === 0 && <p className="text-sm text-slate-500">No citations for this trial.</p>}
                {citationsB.map((citation) => (
                  <CitationCard key={citation.index} citation={citation} />
                ))}
              </div>
            </div>
          )}

          {otherCitations.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Other evidence</p>
              {otherCitations.map((citation) => (
                <CitationCard key={citation.index} citation={citation} />
              ))}
            </div>
          )}
        </div>
      )}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <TrialComparisonForm />
    </Suspense>
  );
}
