import type { ReactNode } from "react";
import type { DocumentGroup } from "@/lib/group-retrieval-results";
import { formatSourceLabel, formatScore, truncateExcerpt } from "@/lib/citation-format";

/**
 * One card in the trial/publication search results — a document
 * (grouped from one or more retrieved chunks; see
 * lib/group-retrieval-results.ts) with its best-scoring supporting
 * excerpt shown up front and any additional matching excerpts
 * collapsed under a disclosure, so a document that matched on several
 * chunks doesn't crowd out the rest of the results list.
 */
export function DocumentResultCard({ group, action }: { group: DocumentGroup; action?: ReactNode }) {
  const [topExcerpt, ...restExcerpts] = group.excerpts;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-900">{group.title}</p>
          <a
            href={group.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-sky-700 hover:underline"
          >
            {formatSourceLabel(group.sourceType, group.sourceIdentifier)} ↗
          </a>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
          <span title="Reciprocal-rank fusion score">score {formatScore(group.bestScore)}</span>
          {group.matchedBy.map((matcher) => (
            <span key={matcher} className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
              {matcher}
            </span>
          ))}
        </div>
      </div>

      {topExcerpt && (
        <blockquote className="mt-3 border-l-2 border-slate-200 pl-3 text-sm italic text-slate-600">
          &ldquo;{truncateExcerpt(topExcerpt.excerpt, 320)}&rdquo;
        </blockquote>
      )}

      {restExcerpts.length > 0 && (
        <details className="mt-2 text-sm text-slate-500">
          <summary className="cursor-pointer select-none font-medium text-slate-600">
            {restExcerpts.length} more supporting excerpt{restExcerpts.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-2 space-y-2">
            {restExcerpts.map((excerpt) => (
              <li key={excerpt.chunkId} className="border-l-2 border-slate-200 pl-3 italic">
                &ldquo;{truncateExcerpt(excerpt.excerpt, 320)}&rdquo;
              </li>
            ))}
          </ul>
        </details>
      )}

      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
