# Local testing notes

Verified on 2026-09-06 using Docker Compose. The original ZIP built successfully; subsequent navigation and chart fixes are documented below.

## Open the app

- Frontend: http://localhost:3000
- Interactive API docs: http://localhost:8000/docs
- API readiness: http://localhost:8000/health

The API reports `ready: true`, 3,250 skills, 21 roles, and 457 surveyed technologies.

The ZIP includes the trained embeddings, graph, vocabulary, role data, trend data, and resume parser. No training, GPU, external database, or API key is needed for local serving. The root README's claims that the parser/data must be copied or migrated are stale. Pipeline reproduction is separate and needs the original datasets and additional training dependencies.

## Try these flows

1. On the home page, select “Docker · Kubernetes” and click the arrow to get recommendations. Alternatively type each skill and press Enter to add it.
2. Open Roles, choose Data Engineer, and compare gaps for Python and SQL. Try the seniority selector.
3. Open a skill such as Docker from a result to inspect its co-occurrences and associated roles.
4. Open Trends to compare rising and falling technologies.
5. Upload a PDF, DOCX, or TXT resume. Use a text-based PDF; the parser does not implement OCR for scanned pages.

An “API fallback active” or “Preview data” badge means sample data is being shown. Do not treat it as a real model result.

## Service commands

Run from the repository root:

```bash
docker compose up --build -d  # build and start
docker compose ps           # status
docker compose logs -f      # logs; Ctrl+C stops following logs
docker compose stop         # stop services
docker compose start        # start existing containers again
docker compose down         # remove this project's containers and network
```

The browser API URL is baked into the frontend at build time as `http://localhost:8000`. This setup is for a browser on the same computer.

## Verification results

- Frontend production build and TypeScript checks passed.
- Existing `test_api.py`: 47 passed, 0 failed (without the optional resume fixture).
- Existing `test_api_deep.py --slow`: 55 passed, 0 failed, 3 documented limitations (without the optional resume fixture).
- Existing timing checks passed: recommendation cases below 50 ms and role matching below 200 ms inside the container.
- Headless Chrome: live recommendations, role list, Data Engineer gap page, Docker detail, trends, and TXT resume upload worked without browser runtime exceptions or fallback badges.
- Separate generated DOCX and PDF uploads returned HTTP 200 and extracted skills.

To repeat the supplied suites without setting up host Python:

```bash
docker compose exec -T api pip install httpx
docker compose exec -T api python - < test_api.py
docker compose exec -T api python - --slow < test_api_deep.py
```

`httpx` is installed only in the running test container; recreating it requires installing that test dependency again. Logs from this run are in `/tmp/stacksense-api-tests.log` and `/tmp/stacksense-api-deep-tests.log`.

## Issues observed or identified during inspection

- **Slash-containing skill names:** `/skills/Torch%2FPyTorch` returns 404 and its frontend detail page shows fallback data. The API's `{name}` route does not consume embedded slashes; the trend detail route uses the same pattern.
- **Malformed PDF:** a file containing invalid PDF bytes returns HTTP 500. The resume UI catches API failures and shows a sample extraction instead of a useful upload error.
- **Readiness reporting:** `/health` returns HTTP 200 even when `ready` is false, while the Docker health check only checks HTTP status. Read the JSON readiness flag when diagnosing startup problems. The current instance is fully ready.
- **Seniority selector:** the frontend changes displayed support figures locally; it does not request a newly ranked gap list for the selected seniority.
- **Existing documented ranking limitations:** duplicate input skills can change rankings; React profiles can receive Java because those skills co-occur in postings; Python alone produces broad recommendations. These are reported as known limitations by the expanded suite.

This was a local serving and functional review, not a reproduction of the README's model evaluation metrics. The observations in that initial review describe the downloaded project before the fixes below.


## Navigation and chart fixes (2026-09-06)

The slash-name routes, role support bar layout, seniority-specific gap requests/denominators, and skill selection have now been fixed. The earlier observations above describe the original ZIP. Skill and role detail failures now show errors rather than sample evidence. Role links on skill pages navigate to roles, fabricated posting denominators were removed, and skill trend charts use the actual rank series. Scatter labels use collision avoidance and leader lines; the scale is correctly labelled log lift.

Regression checks: `docker compose exec -T api python - < test_ui_api.py`.
Desktop (1440 px) and mobile (390 px) Chrome checks cover Data Engineer and AI/ML Engineer, skill search/selection, Torch/PyTorch navigation, seniority requests, horizontal page overflow, bar sizing, and browser runtime errors. The existing API suites still pass (47 basic; 55 expanded, 3 known limitations).
