# StackSense

StackSense turns job-posting evidence into practical skill recommendations. Enter the technologies you know, explore role-specific gaps, inspect how skills appear together, and compare market movement without invented salaries or misleading confidence percentages.

This repository contains the StackSense frontend. It is designed to connect to the separate StackSense API described below.

## What StackSense does

- Normalizes common skill aliases such as `js` and `k8s` into canonical names.
- Ranks useful adjacent skills from learned co-occurrence patterns.
- Compares a person's current skills with role and seniority profiles.
- Distinguishes commonly requested skills from skills that uniquely define a role.
- Shows rising and falling technology ranks from developer-survey data.
- Analyzes PDF, DOCX, and TXT resumes by where skill evidence appears.
- Keeps unrecognized skills and resume terms visible instead of silently discarding them.
- Labels posting aggregation as **From postings** and model output as **Predicted**.

## Evidence principles

StackSense is intentionally careful about what its data can support:

- Support percentages should include their posting denominator.
- Recommendation scores are relative rankings, not probabilities.
- Developer-survey sentiment is not presented as employer demand.
- Missing trend data produces no trend indicator.
- Trends observed for fewer than four years are not charted.
- Salary estimates, employer rankings, and company recommendations are not included without a reliable supporting dataset.

## Application routes

| Route | Purpose |
|---|---|
| `/` | Enter known skills and receive ranked recommendations |
| `/roles` | Browse roles grouped by work family and posting count |
| `/roles/[name]` | Analyze held and missing skills for a role and seniority level |
| `/skills/[name]` | Inspect one skill's neighbors, roles, and survey movement |
| `/trends` | Compare rising, falling, and high-desire-gap technologies |
| `/resume` | Upload a resume for evidence extraction, role matching, and recommendations |

## Technology

- [Next.js](https://nextjs.org/) 16 with the App Router
- React 19
- TypeScript
- Tailwind CSS 4
- Lucide React
- Lightweight, hand-drawn SVG visualizations
- `d3-scale` and `d3-shape` for chart mathematics as the data visualizations evolve

The application uses native `fetch` for API communication. A large charting library is unnecessary for the current bars, sparklines, and scatter plot.

## Getting started

### Requirements

- Node.js 20.9 or newer
- npm
- The StackSense backend for live results

### Install and run

```bash
git clone https://github.com/JohnBlakeSaturn/stacksense-frontend.git
cd stacksense-frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment configuration

Create `.env.local` in the project root:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If `NEXT_PUBLIC_API_URL` is not set, the frontend defaults to `http://localhost:8000`.

Only place browser-safe configuration in variables beginning with `NEXT_PUBLIC_`. Next.js embeds those values into client-side assets; never use them for API secrets or private credentials.

## Backend API

The frontend expects the following endpoints:

| Method | Endpoint | Used by |
|---|---|---|
| `GET` | `/health` | Backend readiness and dataset counts |
| `POST` | `/skills/normalize` | Skill alias resolution |
| `POST` | `/recommend/skills` | Ranked skill recommendations |
| `GET` | `/skills/{name}` | Individual skill evidence |
| `GET` | `/roles` | Role index and seniority counts |
| `POST` | `/roles/gap` | Role-specific held and missing skills |
| `POST` | `/roles/match` | Coverage-ranked role matches |
| `GET` | `/trends` | Rising or falling technology lists |
| `GET` | `/trends/{name}` | Individual rank history and survey context |
| `POST` | `/resume/analyze` | Multipart resume analysis |

The API base URL is centralized in `src/lib/api.ts`.

### Recommendation request

```json
{
  "skills": ["Python", "Docker"],
  "top_k": 10,
  "target_role": "Data Engineer",
  "method": "hybrid"
}
```

`target_role` is optional. The returned `score` controls rank order only and must not be displayed as a match percentage.

### Role-gap request

```json
{
  "skills": ["Python", "SQL"],
  "role": "Data Engineer",
  "top_k": 15
}
```

The initial request omits seniority. Each result can contain a `by_seniority` map, allowing the frontend to animate between available levels without making another request.

### Resume upload

`POST /resume/analyze` accepts `multipart/form-data`. The file must be sent under the `file` field and should be PDF, DOCX, or TXT.

The result supplies:

- Skills grouped by resume section
- Evidence weights and elementary-skill markers
- Unmatched terms
- Ranked recommendations
- The closest role profiles

The backend remains responsible for authoritative file-type, file-size, and content validation.

## Development preview data

The backend was not available during the initial frontend implementation. The application therefore includes deliberately visible development fallbacks so its interactions and layouts can be reviewed offline.

Fallback behavior is never silent:

- Source locations have `FALLBACK` comments.
- A visible **API fallback active** or **Preview data** badge appears.
- Preview figures must not be interpreted as current market evidence.

Find all fallback locations with:

```bash
rg -n "FALLBACK|fallback|API fallback|Preview data" src
```

Before production, replace catch-to-preview behavior with proper loading, empty, error, and retry states. Useful fixture data should move into automated tests or component stories.

## Project structure

```text
src/
├── app/
│   ├── page.tsx                  Home and skill recommendations
│   ├── resume/page.tsx           Resume analysis
│   ├── roles/page.tsx            Role picker
│   ├── roles/[name]/page.tsx     Role gap analysis
│   ├── skills/[name]/page.tsx    Skill details
│   ├── trends/page.tsx           Market movement
│   ├── globals.css               Design tokens and shared layout rules
│   └── layout.tsx                Root layout and metadata
├── components/                   Shared controls and visualizations
├── contexts/                     Theme-provider compatibility layer
├── hooks/                        Performance utilities
└── lib/api.ts                    Typed API client and development fixtures
```

## Design language

StackSense is designed as an instrument over a dataset rather than a generic career-coaching dashboard.

- Warm off-white paper and near-black text
- Deep blue for links, actions, and structure
- Muted blue for skills already held
- Burnt orange only for gaps and falling signals
- Deep teal only for rising signals
- Newsreader for major statements and Inter Tight for interface text
- Hairline separators and comparative bars instead of repeated rounded cards
- A recurring two-column split between existing evidence and missing demand

Motion is limited to actions that benefit from it: drawing first results, changing seniority values, and adding or removing skill chips. Reduced-motion preferences are respected.

## Available scripts

```bash
npm run dev      # Start the development server
npm run lint     # Run ESLint
npm run build    # Create and type-check a production build
npm start        # Run the production build
npm audit        # Check dependencies for known vulnerabilities
```

Before pushing a change, run:

```bash
npm run lint
npm run build
npm audit
```

## Current integration priorities

1. Verify every response type in `src/lib/api.ts` against the running backend.
2. Handle the backend's model-loading cold start through `/health`.
3. Provide a complete skill-vocabulary endpoint for client-side autocomplete.
4. Replace runtime preview fallbacks with real error and retry states.
5. Scale recommendation bars using an explicit corpus denominator or present them as counts.
6. Implement sibling-role comparison using two `/roles/gap` responses.
7. Add component, API-contract, accessibility, and end-to-end tests.
8. Tighten backend CORS to the deployed frontend origin.

## Contributing

1. Create a focused branch from the current default branch.
2. Keep API response types explicit.
3. Preserve the distinction between measured posting evidence and predicted rankings.
4. Do not hide unknown inputs or missing data.
5. Run lint, build, and audit before opening a pull request.
6. Describe any API contract changes in the pull request.

## Security and privacy

- Do not commit `.env.local`, credentials, tokens, or uploaded resumes.
- Do not send resumes to unapproved third-party services.
- Do not log resume contents or personally identifying data by default.
- Validate uploads on both the client and server.
- Keep the lockfile committed and review dependency advisories regularly.
- Use HTTPS for both frontend and backend in production.

## Status

The frontend routes and API client are implemented. Live backend integration, production error handling, and automated tests remain active development work.
