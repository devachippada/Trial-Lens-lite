import type { Citation } from "@/lib/api-types";
import { formatSourceLabel, formatSourceTypeName, truncateExcerpt } from "@/lib/citation-format";

/**
 * One validated citation from a Claude-generated answer (POST
 * /api/v1/ask or /compare) — the excerpt shown here is the actual
 * retrieved chunk text the backend's citation validator confirmed the
 * answer's [n] marker points to (see backend/app/generation/validation.py),
 * not a snippet this page invents.
 */
export function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div
      id={`citation-${citation.index}`}
      className="scroll-mt-24 rounded-lg border border-slate-200 bg-white p-4 shadow-sm target:ring-2 target:ring-sky-400"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
          [{citation.index}] {formatSourceTypeName(citation.source_type)}
        </span>
        <a
          href={citation.source_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs font-medium text-sky-700 hover:underline"
        >
          {formatSourceLabel(citation.source_type, citation.source_identifier)} {"↗"}
        </a>
      </div>
      <p className="mt-2 text-sm font-medium text-slate-900">{citation.title}</p>
      <blockquote className="mt-2 border-l-2 border-slate-200 pl-3 text-sm italic text-slate-600">
        &ldquo;{truncateExcerpt(citation.excerpt, 500)}&rdquo;
      </blockquote>
    </div>
  );
}
