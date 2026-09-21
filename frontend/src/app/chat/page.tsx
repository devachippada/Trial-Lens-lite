"use client";

import { useState } from "react";
import { askQuestion } from "@/lib/api";
import type { AnswerResponse } from "@/lib/api-types";
import { LoadingState } from "@/components/LoadingState";
import { ErrorState } from "@/components/ErrorState";
import { AnswerStatusNotice } from "@/components/AnswerStatusNotice";
import { CitedAnswer } from "@/components/CitedAnswer";
import { CitationCard } from "@/components/CitationCard";

interface Exchange {
  id: string;
  question: string;
  state: "loading" | "error" | "done";
  error?: string;
  answer?: AnswerResponse;
}

/**
 * A transcript of independent question/answer exchanges against
 * POST /api/v1/ask. This is presented as a chat, but the backend
 * itself has no conversation memory (see lib/api.ts's askQuestion
 * docstring) — each question is answered from retrieved evidence
 * alone, not from earlier turns in this transcript. That's called out
 * in the page copy below rather than left implied, since a real chat
 * product would normally carry context forward.
 */
export default function EvidenceChatPage() {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);

  async function ask(q: string) {
    if (!q.trim()) return;
    const id = `${Date.now()}-${Math.random()}`;
    setExchanges((current) => [...current, { id, question: q, state: "loading" }]);
    setQuestion("");

    const result = await askQuestion(q);

    setExchanges((current) =>
      current.map((exchange) =>
        exchange.id === id
          ? result.ok
            ? { ...exchange, state: "done", answer: result.data }
            : { ...exchange, state: "error", error: result.error }
          : exchange
      )
    );
  }

  function retry(exchange: Exchange) {
    setExchanges((current) => current.filter((e) => e.id !== exchange.id));
    void ask(exchange.question);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Evidence chat</h1>
        <p className="mt-1 text-sm text-slate-600">
          Ask a question and get an answer grounded only in retrieved, cited evidence — or an
          honest &ldquo;not enough evidence.&rdquo; Each question is answered independently; earlier
          questions in this transcript aren&rsquo;t used as context for later ones.
        </p>
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What was the primary endpoint?"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!question.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      {exchanges.length === 0 && (
        <p className="text-sm text-slate-500">Ask a question to get started.</p>
      )}

      <ul className="flex flex-col gap-6">
        {exchanges
          .slice()
          .reverse()
          .map((exchange) => (
            <li key={exchange.id} className="flex flex-col gap-3">
              <p className="font-medium text-slate-900">{exchange.question}</p>

              {exchange.state === "loading" && <LoadingState label="Retrieving evidence and asking Claude…" />}

              {exchange.state === "error" && exchange.error && (
                <ErrorState message={exchange.error} onRetry={() => retry(exchange)} />
              )}

              {exchange.state === "done" && exchange.answer && (
                <div className="flex flex-col gap-3">
                  <AnswerStatusNotice status={exchange.answer.status} warnings={exchange.answer.warnings} />
                  {exchange.answer.status === "answered" && exchange.answer.answer && (
                    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                      <CitedAnswer text={exchange.answer.answer} />
                    </div>
                  )}
                  {exchange.answer.citations.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Supporting evidence
                      </p>
                      {exchange.answer.citations.map((citation) => (
                        <CitationCard key={citation.index} citation={citation} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </li>
          ))}
      </ul>
    </main>
  );
}
