import { splitAnswerIntoSegments } from "@/lib/citation-format";

/**
 * Renders a generated answer's text with its "[n]" citation markers as
 * links that jump to the matching CitationCard below, instead of
 * showing the raw bracket syntax the model wrote.
 */
export function CitedAnswer({ text }: { text: string }) {
  const segments = splitAnswerIntoSegments(text);

  return (
    <p className="whitespace-pre-wrap text-slate-800">
      {segments.map((segment, i) =>
        segment.citationIndices ? (
          <a
            key={i}
            href={`#citation-${segment.citationIndices[0]}`}
            className="font-medium text-sky-700 no-underline hover:underline"
          >
            {segment.text}
          </a>
        ) : (
          <span key={i}>{segment.text}</span>
        )
      )}
    </p>
  );
}
