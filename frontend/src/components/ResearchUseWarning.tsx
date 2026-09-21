/**
 * Persistent, site-wide banner (rendered from layout.tsx on every
 * page). Mirrors the project's design commitment to refuse
 * individualized medical advice — this is the one-line version of that
 * commitment, shown before anyone reaches a search box or the chat.
 */
export function ResearchUseWarning() {
  return (
    <div role="note" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900">
      <strong className="font-semibold">Research use only.</strong> TrialLens Lite is a portfolio
      project, not a medical device, and does not give individualized medical advice. Speak with a
      licensed clinician about any treatment decision.
    </div>
  );
}
