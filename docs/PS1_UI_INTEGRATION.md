# PS1 optimiser UI integration

Open **PS1 · Hackathon dataset** in the existing main page. Load the organiser dataset or import the eight input CSVs, open **Connection and saved instances**, set the FastAPI address and planner identity, then explicitly **Save dataset**. The Scenario A planning engine appears inside the PS1 workspace.

## Workflow

1. Select Scenario A. Scenarios B/C still support the existing submission-validation workflow, but cannot generate schedules.
2. Set solver time, physical-night count and optional advanced settings. Generate a schedule.
3. The synchronous request returns only after the backend saves its terminal result. The UI then loads the saved detail, all accesses and all occupancy pages.
4. Select any saved run. The six tabs contain schedule, occupancy, contract results, validation, diagnostics and exact saved CSV downloads.
5. Click an access to inspect its occupancy footprint and highlight matching Alpha/Beta stations. The exact location IDs also appear in the inspector and supply table.
6. Select **Use as baseline** on an accepted run to prefer those placements in a new solve. **Lock for next run** adds a hard placement constraint. Removing a next-run lock never edits an immutable historical run.
7. Generate again to create a new attempt with a new idempotency key. On a transport failure, **Retry exact attempt** resends a frozen copy of the original body/key, even when the form has since changed.
8. After browser refresh, reopen the saved instance using **Load saved list**, then select its saved run. History and schedule data are fetched from FastAPI, not browser persistence.

## Data and request handling

- Reuses `RailPlanClient` and generated input/placement types. Small Zod boundary schemas narrow the API's intentionally generic record objects; no new server contract was introduced.
- Every intentional solve gets a UUID idempotency key. Original unresolved request settings are visible in a disclosure.
- Stop waiting aborts the browser request only. The server may still finish and save the run. Refresh history or retry the exact attempt to recover it.
- Changing instance, connection or planner identity aborts requests and clears component caches. Selected-run requests also cancel previous detail/artifact loads.
- All access/occupancy pages load at limit 200. A premature empty or duplicate-only page reports an incomplete response instead of silently displaying a partial schedule.
- Timeline concurrency uses `physical_night`. Occupancy joins use activity + week. Local access indices and location/week co-sharing groups are never used as global night identifiers.
- Run detail is cached in memory per mounted workspace. Reload explicitly retrieves it from the server. Artifacts are loaded on demand; a failed refresh removes old downloadable files from view.
- Contract scores and dates are taken from saved result data. Browser calculations are limited to sorting, display and converting the stored fractional objective gap to a percentage.
- All accepted, failed, bounded and rejected outcomes remain inspectable. UNKNOWN is not an infeasibility proof. Internal publishability is not official acceptance or operational permission.
- Screenshots and browser tests use clearly isolated mocked HTTP responses. Production components have no fallback/mock schedule source.

## Local setup

Use the existing backend `docs/PS1_PERSISTENCE_TEST_GUIDE.md` first. Apply migration 0007 or the current head to your development database, seed the development planner identity, then start FastAPI. The UI requires the existing CORS settings to allow its local origin. The default UI backend is `http://127.0.0.1:8000`.

From the project root, install using the existing pnpm lockfile and start:

```bash
pnpm install --frozen-lockfile
npm run dev
```

The optimiser defaults are 20 seconds, deterministic limit 10, seed 0 and seven abstract physical nights per week. The input ranges match the existing FastAPI `OptimiseInput` model.

## Automated checks

From the project root:

```bash
npm run test:ps1
npx tsc --noEmit --strict
npm run build
```

From `railplan-backend/frontend`:

```bash
npm test
```

From `railplan-backend`, in its Python environment:

```bash
python -m pytest -q -rs
```

The existing rollback, committed and migration PostgreSQL tests require three separate disposable databases. Follow the existing persistence test guide rather than pointing tests at development or production data.

## Browser regression and screenshots

The browser test is a standalone Node script using Playwright. Install Playwright in a separate test-tools directory if it is not already available; this does not change application dependencies:

```bash
npm install --prefix .test-tools --no-package-lock playwright@1.51.1
node .test-tools/node_modules/playwright/cli.js install chromium
```

Start the UI on port 3011 in another terminal:

```bash
npm run dev -- --hostname 127.0.0.1 --port 3011
```

PowerShell:

```powershell
$env:RAILPLAN_PLAYWRIGHT_MODULE = (Resolve-Path .test-tools/node_modules/playwright).Path
npm run test:ps1:browser
```

Bash:

```bash
RAILPLAN_PLAYWRIGHT_MODULE="$PWD/.test-tools/node_modules/playwright" npm run test:ps1:browser
```

Override `RAILPLAN_UI_URL` if the development URL differs. The script intercepts PS1 HTTP requests and asserts the UI behavior; it is not a database test. It writes screenshots to `docs/ui-screenshots`.

## Still separate work

Live PostgreSQL migration/persistence verification, operational approval, production authentication, Scenario B/C optimisation, background jobs and Ollama/Qwen3 copilot are outside this integration. No backend solver, validator, organiser CSV or migration is changed.
