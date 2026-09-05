# StackSense frontend — architecture and handoff guide

This document is the durable technical handoff for the StackSense frontend. It is intended to give a future developer or coding agent enough context to move this application into a combined frontend/backend repository, wire it to the real API, preserve its visual language, and continue improving it without reintroducing misleading data.

## 1. Product purpose

StackSense helps students and working developers decide what skill to learn next. Its evidence comes from a market dataset containing job postings, extracted skills, co-occurrence relationships, role profiles, seniority profiles, and Stack Overflow survey trends.

The core product promise is evidence rather than generic career coaching:

- Job-market percentages must be traceable to postings.
- Every support percentage should show its denominator.
- Aggregated posting evidence and learned-model output must be labelled differently.
- Model scores are relative ranking scores, not probabilities or calibrated confidence.
- Unknown or unresolved resume terms must remain visible.
- Salary figures and employer rankings are outside the supported dataset and must not be invented.

The repository may still be named after an earlier project, but the product name shown to users is **StackSense**.

## 2. Current implementation status

The frontend is a Next.js App Router application. All intended API paths have been implemented in the typed client at `src/lib/api.ts`.

The backend was unavailable while the frontend was developed. Consequently, the UI contains explicit development fallbacks. These fallbacks:

- Keep all pages visually testable without a running API.
- Are marked with `FALLBACK` comments in source code.
- Display an `API fallback active` or `Preview data` badge to users.
- Must not be mistaken for real market evidence.
- Should be removed, gated behind an explicit development flag, or converted into fixtures before production release.

The current application passes:

```bash
npm run lint
npm run build
npm audit
```

At the time of this handoff, `npm audit` reports zero known vulnerabilities.

## 3. Technology stack

- Next.js 16 App Router
- React 19
- TypeScript with strict mode
- Tailwind CSS 4 is installed, although much of the bespoke design uses CSS variables and scoped JSX styles.
- Lucide React for small interface icons.
- Framer Motion is installed for future interaction work. Most current motion is deliberately implemented with CSS to keep it restrained.
- `d3-scale` and `d3-shape` are installed for chart mathematics. The current simple SVG components do not yet require the full APIs, but these dependencies are retained to support real-data chart scaling during wiring.
- ESLint 9 with the Next.js core-web-vitals and TypeScript flat configurations.

Large chart libraries, Axios, Markdown renderers, and unused Radix packages were removed. Native `fetch` is used for API requests.

## 4. Repository structure

```text
src/
├── app/
│   ├── globals.css              Global tokens, layout helpers, responsive rules
│   ├── layout.tsx               Fonts, metadata, navbar, error boundary, footer
│   ├── page.tsx                 Home skill input and recommendations
│   ├── resume/page.tsx          Resume upload, evidence, role matches, recommendations
│   ├── roles/page.tsx           Grouped role picker
│   ├── roles/[name]/page.tsx    Role gap analysis and seniority comparison
│   ├── skills/[name]/page.tsx   Individual skill evidence
│   └── trends/page.tsx          Rising/falling skills and desire gap
├── components/
│   ├── ErrorBoundary.tsx        Application-level client error boundary
│   ├── Footer.tsx
│   ├── LiftScatter.tsx          Support versus lift SVG chart
│   ├── LoadingSpinner.tsx       Retained utility
│   ├── MechanismBadge.tsx       `From postings` versus `Predicted`
│   ├── Navbar.tsx
│   ├── RolePicker.tsx
│   ├── SeniorityToggle.tsx
│   ├── SkillInput.tsx           Token input, normalization, local suggestions
│   ├── SupportBar.tsx           Primary support visualization
│   ├── ThemeToggle.tsx          Retained no-op compatibility utility
│   └── TrendLine.tsx            Rank-series sparkline
├── contexts/ThemeContext.tsx    Retained light-only provider shape
├── hooks/usePerformance.ts      Retained performance/network hook
└── lib/api.ts                   API URL, response types, methods, development fixtures
```

Obsolete `/student`, `/professional`, and `/tech/[tech]` routes were removed. Resume analysis is now one flow, and skill pages live at `/skills/[name]`.

## 5. Environment and local commands

The only required public environment variable is:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If it is missing, `src/lib/api.ts` defaults to `http://localhost:8000`.

Common commands:

```bash
npm install
npm run dev
npm run lint
npm run build
npm start
npm audit
```

When copied into a monorepo, preserve the frontend's lockfile if the frontend remains an independent package. If the combined repository uses npm workspaces, move the dependency declarations into the frontend workspace and regenerate the root lockfile rather than copying two conflicting lockfiles.

## 6. Design system

Global tokens are defined in `src/app/globals.css`:

| Token | Value | Meaning |
|---|---:|---|
| `--ink` | `#14161A` | Main text and high-emphasis rules |
| `--paper` | `#FBFAF7` | Main page background |
| `--graph` | `#1B4D8F` | Primary actions, links, structural emphasis |
| `--graph-dim` | `#A8BFD9` | Skills already held and lower-emphasis blue |
| `--signal` | `#C2410C` | Missing skills and falling signals only |
| `--rise` | `#0F766E` | Rising signals only |
| `--rule` | `#DEDAD2` | Borders and separators |
| `--quiet` | `#6B6A66` | Secondary text, captions, and units |
| `--wash` | `#F1EEE7` | Alternate sections and chart tracks |

The accent colours have semantic meanings. Do not use orange and teal decoratively:

- Orange means missing, declining, or caution.
- Teal means rising.
- Deep blue means interaction and structure.
- Muted blue means already held.

Typography:

- Inter Tight is the interface and body family.
- Newsreader is used for hero and major section headings.
- All numeric data uses tabular numeral alignment inherited from `body`.
- Avoid all-caps eyebrow labels and decorative monospace data labels.

Layout:

- `.shell` caps content at 1180px.
- `.section` supplies consistent vertical spacing.
- `.split` is the repeated two-column comparison pattern.
- Pages are left-aligned and use hairline separators rather than collections of rounded cards.
- Responsive layouts collapse to a single column below approximately 760px.

Motion:

- Support bars draw once over 400ms with a 30ms stagger.
- Seniority changes animate bar widths.
- Input chips scale/fade over 150ms.
- `prefers-reduced-motion` disables animations and smooth scrolling.
- Avoid scroll-reveal effects, parallax, animated gradients, count-up figures, and generic hover lift.

## 7. Shared component contracts

### `SkillInput`

Accepts:

```ts
{
  value: Array<{ input: string; canonical: string | null }>;
  onChange: (chips) => void;
  onSubmit?: () => void;
  busy?: boolean;
}
```

Behavior:

- Enter commits the current term.
- Commit calls `POST /skills/normalize`.
- Recognized terms display their canonical spelling.
- Unknown terms stay visible, muted, struck through, and have an explanatory title.
- Suggestions currently filter a small fallback vocabulary. This must be replaced with the full API vocabulary when the backend exposes it.
- The guide mentioned loading all 3,250 names client-side, but the supplied API reference did not define a vocabulary endpoint. Add one to the backend, such as `GET /skills`, rather than sending normalization requests on every keystroke.

### `SupportBar`

Displays skill support as a horizontal bar. Props include skill name, support fraction, optional numerator and denominator, held state, trend, and animation delay.

- Support must be a fraction from 0 to 1.
- Held skills are muted blue; missing skills are orange.
- Hover swaps the displayed percentage for `numerator of denominator` in place.
- Trend arrows appear only when trend data exists.
- The component currently links to a skill route. For role labels, introduce a configurable link target rather than passing a role name as though it were a skill.

### `MechanismBadge`

- Default: `From postings` in blue for exact aggregation.
- `predicted`: `Predicted` in quiet grey for learned model output.

### `SeniorityToggle`

Levels: junior, mid, senior, staff, lead, principal.

Levels backed by fewer than 20 postings are disabled. The title attribute explains the posting count. On role pages, changing seniority reads `by_seniority` values already included in the gap response; it must not cause a refetch.

### `LiftScatter`

Plots role support on the horizontal axis and lift on the vertical axis. Held skills are muted blue and gaps are orange. Upper-left points are role-defining skills: high lift despite lower global frequency.

Before production, use `d3-scale` to compute padded, data-dependent domains and improve label collision handling. The present implementation uses direct SVG arithmetic and alternating labels.

### `TrendLine`

Plots `rank_series`, never raw adoption `series`. Raw shares are not comparable across survey years because respondent counts changed substantially.

- Fewer than four observed years produces explanatory text instead of a chart.
- Captions show slope, latest adoption, and years observed.
- API-provided caveats should be printed verbatim near the chart.

## 8. API client and error behavior

All requests are centralized in `src/lib/api.ts`. The shared request helper:

- Prefixes paths with `NEXT_PUBLIC_API_URL`.
- Sends JSON content type for ordinary requests.
- Does not manually set content type for multipart `FormData`, allowing the browser to create the correct boundary.
- Throws an `Error` for non-2xx responses using the response body when available.

There is currently no retry, timeout, cancellation, or structured error class. During backend wiring, add:

- `AbortController` timeouts for ordinary requests.
- Request cancellation for stale normalization operations.
- Clear handling for 400, 404, 422, and 503.
- A cold-start state for `/health.ready === false` instead of immediately describing it as an ordinary failure.
- User-facing retry controls where appropriate.

### Health

```http
GET /health
```

```ts
{
  ready: boolean;
  errors: string[];
  skills: number;
  roles: number;
  trends: number;
}
```

Called on the home page. Counts feed the hero strip and must not be hard-coded once the API is available. A false `ready` value indicates a backend cold start or engine-loading failure.

### Normalize skills

```http
POST /skills/normalize
Content-Type: application/json

{ "skills": ["js", "k8s"] }
```

Response:

```ts
Array<{
  input: string;
  canonical: string | null;
  category: string | null;
}>
```

`canonical: null` must remain visible as an unresolved chip.

### Recommend skills

```http
POST /recommend/skills

{
  "skills": ["Python", "Docker"],
  "top_k": 10,
  "target_role": "Data Engineer",
  "method": "hybrid"
}
```

`target_role` is optional. Response fields used by the frontend:

```ts
{
  method: string;
  recognised: string[];
  unrecognised: string[];
  target_role?: string;
  recommendations: Array<{
    rank: number;
    skill: string;
    score: number; // ranking only; never show as a percentage
    category: string;
    postings_mentioning: number;
    role_support?: number | null;
    trend?: Trend | null;
  }>;
  note: string;
}
```

The backend-provided `note` is surfaced beneath results. Preserve it.

### Skill details

```http
GET /skills/{name}
```

The name must be URL encoded. Expected response:

```ts
{
  canonical: string;
  category: string;
  in_survey: boolean;
  postings_mentioning: number;
  degree: number;
  trend?: Trend | null;
  co_occurring_distinctive: Array<{
    skill: string;
    pmi: number;
    postings: number;
  }>;
  co_occurring_frequent: Array<{
    skill: string;
    pmi: number;
    postings: number;
  }>;
  roles_requiring: Array<{
    role: string;
    support: number;
    lift: number;
  }>;
}
```

Distinctive neighbors are PMI-ordered. Frequent neighbors are count-ordered. Keep both lists because they answer different questions.

### Roles

```http
GET /roles
```

```ts
{
  roles: Array<{
    name: string;
    postings: number;
    by_seniority: Record<string, number>;
    distinct_skills: number;
  }>;
}
```

The API returns a flat list. `RolePicker` owns presentation grouping. Review the family-matching rules against the exact backend role names; substring grouping is pragmatic but should ultimately become an explicit mapping.

### Role gap

```http
POST /roles/gap

{
  "skills": ["Python", "SQL"],
  "role": "Data Engineer",
  "top_k": 15
}
```

The frontend intentionally omits `seniority` on the initial request so each entry's `by_seniority` map can drive instant local switching.

```ts
{
  role: string;
  postings_analysed: number;
  coverage: number;
  you_have: SkillRef[];
  gaps: SkillRef[];
  note: string;
}
```

This output is posting aggregation, so it receives `From postings`, not `Predicted`.

Sibling role comparison is not fully implemented yet. It requires calling `/roles/gap` with the same skill list for a second role, then diffing the two gap arrays client-side.

### Role match

```http
POST /roles/match

{ "skills": ["React", "TypeScript", "HTML/CSS"] }
```

Expected response:

```ts
{
  recognised: string[];
  roles: Array<{
    role: string;
    coverage: number;
    matched_skills: string[];
    top_missing: string[];
    postings: number;
  }>;
}
```

The resume endpoint already returns the top matches, so the resume page does not call this separately.

### Trends

```http
GET /trends?direction=rising&limit=20
GET /trends?direction=falling&limit=20
GET /trends/{name}
```

Trend list entries include skill, rank slope, latest adoption, years observed, and sometimes desire gap. Individual trend responses contain:

```ts
{
  skill: string;
  series: Record<string, number>;
  rank_series: Record<string, number>;
  rank_slope: number;
  desire_gap: number;
  years_observed: number;
  source: string;
  caveat: string;
}
```

The current trends page renders compact ranked rows rather than fetching every individual series. If sparklines are added to the ranked lists, cache trend-detail calls and avoid a request waterfall.

### Resume analysis

```http
POST /resume/analyze
Content-Type: multipart/form-data
```

The multipart field name is `file`. Accepted formats are PDF, DOCX, and TXT.

```ts
{
  sections_found: Record<string, number>;
  skills: Array<{
    skill: string;
    weight: number;
    section: string;
    matched_text: string;
    elementary: boolean;
    trend?: Trend | null;
  }>;
  unmatched_terms: string[];
  recommendations: Recommendation[];
  role_match: RoleMatch[];
}
```

Evidence grouping is driven by `section`. Experience and projects are strongest evidence; skills lists are weaker; coursework and education are weakest. `elementary: true` reflects a hedge in the resume and should remain visible.

The endpoint may take 2–5 seconds. The current page changes the upload label to `Reading evidence…`; a later iteration should add richer progress and allow already-rendered page content to remain interactive.

## 9. Page behavior

### `/`

- Fetches health once after mount.
- Accepts normalized skill chips.
- Includes three example combinations.
- Calls `/recommend/skills` on submit.
- Renders rank order without exposing raw model score.
- Shows API `note` text.
- Shows live health counts when available.

The current recommendation bars use global posting count normalized against 7,000 for visual width. This is an interim visualization because `postings_mentioning` is a count rather than a support fraction. During wiring, either return corpus size and calculate true support or render counts with a count-scaled chart. Do not describe that interim width as a true share.

### `/roles`

- Calls `/roles`.
- Groups roles into product-facing families.
- Shows posting count for evidence strength.
- Links to encoded dynamic routes.

### `/roles/[name]`

- Fetches the role index for metadata and seniority counts.
- Calls `/roles/gap` for initial skills.
- Defaults to example chips `Python` and `SQL` so the offline page demonstrates itself.
- Re-runs analysis when the user changes skills and submits.
- Splits held and missing evidence into two columns.
- Changes support values locally when seniority changes.
- Renders lift versus support.
- Contains a placeholder explanation for the not-yet-completed sibling comparison.

When connected, decide whether a role page should initially be empty or retain demonstrative example skills. If examples remain, explicitly label them as examples so they cannot be mistaken for a user's profile.

### `/skills/[name]`

- Calls `/skills/{name}`.
- Shows canonical name, category, posting count, and graph degree.
- Shows PMI-ordered and raw-count neighbor lists side by side.
- Shows roles requiring the skill.
- Shows trend only where available.

Role rows currently use `SupportBar`, whose link points to a skill route. Refactor its target before production so clicking a role navigates to `/roles/{role}`.

### `/trends`

- Fetches rising and falling lists concurrently.
- Shows adoption and rank slope.
- Shows desire gap where available.
- Treats the survey-versus-employer caveat as a first-class callout.

The fallback contains illustrative values mentioned in the original frontend plan. They are not presented as live data because the page displays the fallback badge.

### `/resume`

- Uses native file input in a styled drop area.
- Posts multipart data directly to the configured backend.
- Groups recognized skills by evidence section.
- Keeps unmatched terms visible and struck through.
- Shows up to six role matches.
- Shows ranked recommendations without confidence percentages.

Browser-side drag event handling and file validation can be improved. The backend must remain the authority for actual MIME/content validation.

## 10. Fallback inventory and removal plan

Search all fallback locations with:

```bash
rg -n "FALLBACK|fallback|API fallback|Preview data" src
```

Fallback sources currently exist in:

- `src/lib/api.ts`: health, role list, vocabulary, recommendations, and gap fixture builders.
- `src/components/SkillInput.tsx`: local exact-name normalization.
- `src/app/page.tsx`: local recommendation response.
- `src/app/roles/page.tsx`: local role index.
- `src/app/roles/[name]/page.tsx`: local gap response.
- `src/app/skills/[name]/page.tsx`: representative skill detail.
- `src/app/trends/page.tsx`: rising and falling trend arrays.
- `src/app/resume/page.tsx`: representative resume extraction.

Recommended production transition:

1. Wire and validate every endpoint against its page.
2. Add proper error/loading/empty states.
3. Move useful fixtures into test files or Storybook stories.
4. Delete runtime catch-to-fixture behavior.
5. Keep visible error states rather than silently producing sample results.
6. Add end-to-end tests with mocked network responses.
7. Run the legacy-content search and ensure no preview badge appears in production.

Never retain silent automatic fallbacks in production. A real backend failure must be distinguishable from real evidence.

## 11. Moving into a combined frontend/backend repository

A suggested monorepo shape is:

```text
stacksense/
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── ...
├── backend/
│   ├── app or src/
│   ├── tests/
│   └── ...
├── .env.example
├── README.md
└── package.json or orchestration files
```

Migration checklist:

1. Copy the entire frontend project except `.next` and `node_modules`.
2. Preserve `public/test2.svg`; it is the current brand mark and favicon.
3. Preserve `FRONTEND_HANDOFF.md` and the original product/design plan.
4. Add `.env.example` without secrets.
5. Point `NEXT_PUBLIC_API_URL` to the backend origin in development and deployment.
6. If reverse-proxying the backend under the same origin, consider a relative base such as `/api`, but ensure this does not recreate the removed third-party proxy route.
7. Configure backend CORS to the deployed frontend origin. Do not leave wildcard CORS in production.
8. Do not expose server-only credentials through `NEXT_PUBLIC_*`; those variables are embedded in browser assets.
9. Add root commands to start frontend and backend together.
10. Reinstall dependencies rather than copying `node_modules`.
11. Run frontend lint, build, audit, and backend tests from the combined repository.

Example development environment:

```dotenv
# Safe public browser configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Production deployments must use HTTPS for both origins to avoid mixed-content blocking.

## 12. Quality and accessibility expectations

Maintain these invariants during later styling work:

- All buttons and form inputs must be keyboard reachable.
- Icon-only buttons require accessible labels.
- Charts require an accessible label and adjacent textual interpretation.
- Colour must not be the only indicator; arrows, labels, and column headings carry the same meaning.
- Focus indicators must remain visible.
- Responsive layouts must work without horizontal page scrolling.
- Loading and error states must announce meaningful text, not only spinners.
- Reduced-motion users receive complete static information.
- Do not hide unresolved terms or missing trend data.

Known accessibility improvements still worth making:

- Add an `aria-live` region for normalization and analysis results.
- Improve the autocomplete to follow the ARIA combobox/listbox pattern.
- Add keyboard navigation through suggestions.
- Replace title-only seniority explanations with accessible descriptive text.
- Add explicit upload validation messages.
- Test colour contrast and keyboard flow using automated and manual checks.

## 13. Testing recommendations

No automated test suite currently exists. Add tests in this order:

1. API client contract tests for success and each error status.
2. `SkillInput` tests for recognized, normalized, unknown, remove, submit, and keyboard behavior.
3. `SupportBar` tests for denominator swap and absent trend behavior.
4. Role page tests for disabled seniority levels and local bar updates.
5. Resume tests for multipart field name, evidence groups, elementary labels, and unmatched terms.
6. End-to-end happy paths for home, role gap, skill details, trends, and resume.
7. An end-to-end backend-unavailable state confirming no sample data is mistaken for live data.

Good fixture cases:

- `js` normalizes to `JavaScript`.
- `k8s` normalizes to `Kubernetes`.
- An unknown term produces `canonical: null`.
- A trendless skill shows no arrow.
- A skill with fewer than four survey years shows no sparkline.
- A seniority level with 19 postings is disabled; one with 20 is enabled.
- Recommendation score is never followed by `%`.
- Resume terms such as MediaPipe remain visible when unmatched.

## 14. Security and dependency maintenance

- Use `npm audit` after every dependency update.
- Review major framework release notes before upgrading Next.js or React.
- Keep `package-lock.json` committed.
- Avoid reintroducing Axios unless it provides a demonstrated requirement; native fetch covers current needs.
- Validate uploaded file type and size on both client and server.
- The browser must never parse resumes as trusted HTML.
- Never send resume contents to third-party services without explicit user consent and privacy documentation.
- Tighten backend CORS before deployment.
- Add reasonable backend upload limits and request timeouts.
- Do not log uploaded resume contents or personally identifying data by default.

## 15. Known gaps and next wiring tasks

These are the highest-priority tasks when the backend becomes available:

1. Verify every response shape against `src/lib/api.ts`; adjust types rather than casting incompatible responses.
2. Test cold-start handling through `/health` for the backend's 30–60 second model-loading period.
3. Add or identify a full skill-vocabulary endpoint for client-side autocomplete.
4. Replace recommendation bar approximations with an honest scale based on an explicit denominator or use count bars.
5. Implement sibling role comparison by fetching a second gap profile and diffing both.
6. Refactor `SupportBar` to accept a destination type so role rows link to role pages.
7. Fetch full trend detail for sparklines using a cache and bounded concurrency.
8. Replace catch-to-fixture fallbacks with real error states after integration testing.
9. Add structured loading, empty, and retry states.
10. Add automated component and end-to-end tests.
11. Review whether example skills on role pages should persist after wiring.
12. Test real long names, large counts, missing seniority maps, null trends, unknown skills, and 404 pages.

## 16. Product rules that must not regress

- Do not show salary figures unless a real, documented salary dataset is added.
- Do not invent or rank company names.
- Do not turn a model score into a confidence percentage.
- Do not silently discard unrecognized skills or resume terms.
- Do not show a trend arrow when trend data is absent.
- Do not chart a trend with fewer than four observed years.
- Do not imply developer-survey sentiment equals employer demand.
- Do not hide backend-provided explanatory `note` or `caveat` fields.
- Do not use generic card grids where comparative bars or split layouts communicate evidence better.
- Do not add a chatbot, force-directed skill graph, or elaborate onboarding without a demonstrated product requirement.

## 17. Final orientation for a future coding agent

Start by reading this file, the original frontend plan, `src/lib/api.ts`, and `src/app/globals.css`. Then run the application and inspect the backend's OpenAPI document at `/docs` while the server is available.

Before changing presentation, determine whether the requested change affects the meaning of evidence. Preserve the distinction between exact posting aggregation and prediction, keep denominators visible, and prefer an honest missing state over fabricated completeness.

The current frontend is intentionally a restrained, quantitative instrument: warm paper, dark ink, blue structure, orange gaps, teal rises, hairline rules, two-column comparisons, and minimal purposeful motion. Later visual refinement is welcome, but these semantic rules are the foundation of the product rather than incidental styling.
