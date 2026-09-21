import Link from "next/link";
import { getBackendStatus } from "@/lib/api";

const FEATURES = [
  {
    href: "/trials",
    title: "Trial search",
    description: "Search ingested ClinicalTrials.gov records and see the supporting excerpts for each match.",
  },
  {
    href: "/publications",
    title: "Publication search",
    description: "Search ingested PubMed publications the same way.",
  },
  {
    href: "/chat",
    title: "Evidence chat",
    description: "Ask a question and get a cited, evidence-only answer — or an honest “not enough evidence.”",
  },
  {
    href: "/compare",
    title: "Compare trials",
    description: "Compare two registered trials side by side, grounded in their own ingested text.",
  },
] as const;

export default async function HomePage() {
  const backend = await getBackendStatus();

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-12">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">TrialLens Lite</h1>
        <p className="mt-2 text-slate-600">
          A clinical-trial literature assistant. It searches ingested ClinicalTrials.gov and
          PubMed records, retrieves relevant evidence, and answers questions using only that
          retrieved evidence, with validated citations back to the source.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <span
            className={`h-2.5 w-2.5 rounded-full ${backend.ok ? "bg-emerald-500" : "bg-red-500"}`}
            aria-hidden
          />
          <span className="font-medium">Backend: {backend.ok ? "ready" : "not ready"}</span>
        </div>
        <p className="mt-1 text-sm text-slate-500">{backend.detail}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {FEATURES.map((feature) => (
          <Link
            key={feature.href}
            href={feature.href}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
          >
            <p className="font-semibold text-slate-900">{feature.title}</p>
            <p className="mt-1 text-sm text-slate-600">{feature.description}</p>
          </Link>
        ))}
      </div>
    </main>
  );
}
