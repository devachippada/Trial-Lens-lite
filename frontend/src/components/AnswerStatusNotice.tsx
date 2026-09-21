import type { AnswerStatus } from "@/lib/api-types";

/**
 * Explains a non-"answered" AnswerResponse.status to the user in plain
 * language. Text mirrors the actual backend behavior it's describing
 * (backend/app/generation/answer.py's INSUFFICIENT_EVIDENCE_MESSAGE /
 * VALIDATION_FAILED_MESSAGE) rather than inventing separate copy — this
 * is what "insufficient-evidence behavior" and fail-closed citation
 * validation actually look like from the UI.
 */
const COPY: Record<Exclude<AnswerStatus, "answered">, { title: string; tone: string; body: string }> = {
  insufficient_evidence: {
    title: "Not enough evidence",
    tone: "border-amber-200 bg-amber-50 text-amber-900",
    body: "The retrieved evidence doesn't support an answer to this question. Try rephrasing it, or ask about a specific ingested trial or publication.",
  },
  validation_failed: {
    title: "Answer withheld",
    tone: "border-red-200 bg-red-50 text-red-800",
    body: "The generated answer didn't cite only real, retrieved evidence, so it isn't shown — this protects against unsupported or fabricated claims. Try rephrasing the question.",
  },
};

export function AnswerStatusNotice({ status, warnings }: { status: AnswerStatus; warnings: string[] }) {
  if (status === "answered") return null;
  const copy = COPY[status];

  return (
    <div role="status" className={`rounded-lg border p-4 ${copy.tone}`}>
      <p className="font-medium">{copy.title}</p>
      <p className="mt-1 text-sm">{copy.body}</p>
      {warnings.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs opacity-80">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
