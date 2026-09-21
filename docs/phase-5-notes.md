# Phase 5 notes

What Phase 5 built: a trial search page, a publication search page, an
evidence chat page, citation cards with supporting excerpts, a trial
comparison view, loading and error states throughout, and a persistent
research-use-only warning banner. Everything calls the existing backend
APIs from Phases 3–4 (`GET /api/v1/retrieve`, `POST /api/v1/ask`,
`POST /api/v1/compare`) — no backend code changed, and no page shows
placeholder, mocked, or invented data.

## A judgment call worth flagging: there's no trial/publication search endpoint

The backend has `GET /api/v1/retrieve` (chunk-level full-text/dense/
hybrid search), `POST /api/v1/ask` (Q&A), and `POST /api/v1/compare`
(two named trials) — there is no `GET /api/v1/trials?q=...`-style
endpoint that lists or searches `Trial`/`Publication` rows by metadata.
Since the instruction was to use the existing backend APIs and not
fabricate responses, both search pages are built on
`GET /api/v1/retrieve`: they search chunks and group the results by
`source_identifier`/`source_type` back into one card per document
(`src/lib/group-retrieval-results.ts`). That's an honest, real search
over ingested content — every card's excerpt, score, and link is data
the backend actually returned — but it's worth being explicit that it's
chunk-level retrieval grouped client-side, not a dedicated document
search. If a future phase adds a real trials-listing endpoint, these
two pages are the ones to point at it instead.

The evidence chat is similarly honest about a real limitation: `POST
/api/v1/ask` has no conversation memory (Phase 4 designed it
stateless), so the chat page keeps a local transcript of independent
question/answer exchanges rather than claiming earlier turns inform
later answers — the page copy says so directly instead of implying a
multi-turn context window that doesn't exist.

The trial comparison view groups the returned citations into "Trial A"
and "Trial B" columns by comparing each citation's `source_identifier`
to the two entered NCT numbers — this works because
`assemble_trial_chunks` (backend/app/generation/comparison.py) sets a
chunk's `source_identifier` to its own trial's NCT id, so the frontend
never has to guess which half of a flat citation list belongs to which
trial.

## What was actually built

- `src/lib/api-types.ts` — TypeScript mirrors of the backend's Pydantic
  response models.
- `src/lib/api-result.ts` — pure response/error parsing (FastAPI's two
  error shapes — a plain `detail` string, or a list of pydantic
  validation errors on a 422 — normalized to one message).
- `src/lib/api.ts` — typed fetch wrappers (`retrieveEvidence`,
  `askQuestion`, `compareTrials`) that never throw; every page renders
  `ApiResult`'s real `ok`/`error` rather than assuming success.
- `src/lib/group-retrieval-results.ts` — groups retrieval hits into
  per-document cards (see above).
- `src/lib/citation-format.ts` — source labels, RRF score formatting,
  word-boundary excerpt truncation, and splitting an answer into
  plain-text/citation-marker segments so `[1]` renders as a link to its
  citation card instead of raw bracket syntax.
- `src/lib/validation.ts` — client-side NCT-format/duplicate-trial
  validation for the comparison form, so a malformed request never
  reaches the backend.
- `src/components/`: `ResearchUseWarning` (site-wide banner, every
  page), `SiteNav`, `LoadingState`, `ErrorState`, `CitationCard`
  (citation + its real supporting excerpt), `DocumentResultCard`
  (search result card with a collapsible "N more excerpts"),
  `AnswerStatusNotice` (renders the backend's actual
  `insufficient_evidence`/`validation_failed` copy and warnings —
  nothing invented), `CitedAnswer` (renders `[n]` markers as jump
  links).
- `src/app/trials/page.tsx`, `publications/page.tsx`, `chat/page.tsx`,
  `compare/page.tsx` — the four feature pages, all Client Components
  (search-on-submit and chat/compare are inherently interactive; the
  homepage stays a Server Component). Loading/error states are
  per-request local component state, not Next's route-level
  `loading.tsx`/`error.tsx`, since nothing here is server-rendered data
  fetching during navigation — every fetch happens after a user
  action, which is what `useState` + inline states are for.
- `vitest.config.ts` and `package.json`'s new `test` script/`vitest`
  devDependency, plus four test files under `src/lib/__tests__/`
  covering the pure modules above.

## What was actually verified, and how

Same sandbox as every backend phase, re-confirmed rather than assumed:
`npm install` fails immediately with `E403`/`E401` against both the
public npm registry and the one internal registry this environment can
even reach (which requires credentials this session doesn't have) — so
`node_modules` cannot be populated, and `next build`, `next lint`, and
`vitest run` cannot actually execute here, exactly the same category of
gap as `pip install sqlalchemy` in the backend phases.

What's different from the backend phases, and better than expected:
this sandbox does have global Node tooling available (Node 22, and a
global `typescript` package — installed for unrelated tooling, not this
project) that made real verification possible anyway:

- **Every one of the 27 TypeScript/TSX files under `src/`, plus
  `vitest.config.ts` and `tailwind.config.ts`, was syntax-checked for
  real** using the TypeScript compiler's `transpileModule` in
  syntax-only mode (no type-checking, since `next`/`react`/`vitest`'s
  type declarations aren't installed — this is the TS equivalent of
  Python's `py_compile`, checking parseability, not types). All 26 of
  this project's own files passed with zero syntax errors on the first
  attempt. (The 27th, `next-env.d.ts`, is a pre-existing Next.js
  auto-generated file containing only triple-slash reference
  directives; the compiler's transpile-to-JS step has nothing to emit
  for a file with no statements and crashed on it — a tool limitation
  on an empty, unmodified, auto-generated file, not a defect in
  anything this phase wrote.)
- **Every assertion in all four pure-logic test files
  (`api-result.test.ts`, `group-retrieval-results.test.ts`,
  `citation-format.test.ts`, `validation.test.ts`) was executed for
  real**, not just written: each `lib/*.ts` module was transpiled to
  plain CommonJS with the same TypeScript compiler and required
  directly into a Node script asserting the exact same cases the
  vitest files declare (response parsing for both FastAPI error
  shapes, grouping/sorting/deduplication of retrieval hits, citation
  marker splitting and excerpt truncation, and NCT-format/self-
  comparison validation). All passed on the first run.

Not verified in this environment (blocked by the registry access this
sandbox doesn't have, not a known defect):

- `next build` / `next dev` — needs `next`, `react-dom`, and their
  transitive dependencies installed.
- `next lint`, `tsc --noEmit` — needs `next`'s and `react`'s type
  declarations to type-check against (the syntax check above doesn't
  substitute for this: it can't catch a wrong prop name or a
  mismatched `ApiResult` type, only a malformed file).
- `vitest run` — needs the `vitest` package; the manual
  transpile-and-require above proves the *logic* those test files
  assert on, but not that `vitest`'s own runner/reporter would parse
  and execute the actual `.test.ts` files without modification.
- Rendering any component in a real browser or DOM — no page,
  including the four new ones, has been visually confirmed to render
  correctly, only to be syntactically valid TSX calling the right
  props.
- An actual round trip against the live backend (search returning real
  ingested results, chat producing a real Claude answer, comparison
  citations actually splitting into the right columns) — needs both
  `npm install` here and the backend's own unresolved gaps
  (`sqlalchemy`/`pgvector`/`anthropic`, per `docs/phase-2-notes.md`
  through `phase-4-notes.md`) to be resolved in a real environment
  first.

## Commands to finish verification yourself

```bash
cd frontend
npm install          # now includes vitest as a devDependency
npm run typecheck    # tsc --noEmit against real next/react types
npm run lint
npm test             # vitest run — the four suites above, for real
npm run build

# with the backend running (see docs/phase-1-notes.md through phase-4-notes.md)
# and NEXT_PUBLIC_API_URL pointed at it:
npm run dev
# then visit /trials, /publications, /chat, and /compare in a browser
```

If `npm run typecheck` surfaces something the syntax check above
couldn't have caught (a prop mismatch, a wrong import), that's the real
signal to act on — the syntax check in this sandbox was never a
substitute for it, only the closest real verification available without
`node_modules`.
