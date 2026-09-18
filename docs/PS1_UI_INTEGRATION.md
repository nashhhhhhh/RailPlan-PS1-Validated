# PS1 optimiser UI integration

Select **Open optimiser** on the dashboard. Load the organiser dataset or import its eight
source CSVs. Stateless inspection and Scenario A preview work without a database. Persisted
instances, history and jobs require FastAPI at migration head 0009 and a planner identity.

## Workflow

1. Load/import the eight input CSVs and inspect their lineage and network topology.
2. Select Scenario A, configure bounded solver options, and generate a schedule. Scenario B
   and C remain available for submission validation; this checkout has no B/C optimiser
   modules and the UI cannot accidentally send them to the A endpoint.
3. Accepted candidates expose schedule, occupancy, contract, validation and exact CSV tabs.
   UNKNOWN, INFEASIBLE and rejected outcomes remain diagnostic and expose no CSV downloads.
4. Select an access to inspect its occupied locations. Timeline concurrency uses
   `physical_night`; occupancy joins use activity + week.
5. Accepted saved runs can be baselines. A lock is an explicit hard assignment for the next
   run; it never edits immutable history.
6. After refresh, reopen the saved instance and result from FastAPI. Mock data is never used
   as a production fallback.

`access_night` is local to a contract/activity-type/week. `co_share_group` is local to a
location/week. Neither proves global concurrency. Internal publishability does not assert
official acceptance or operational permission.

## Local setup

The project-root launcher is the beginner path:

```powershell
python app.py
```

For separate processes:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Start FastAPI separately on port 8000 and allow the frontend origin in
`RAILPLAN_CORS_ORIGINS`. Apply migration 0009 before using persisted features.

## Automated checks

```powershell
corepack pnpm exec tsc --noEmit
corepack pnpm test:ps1
corepack pnpm build
```

For the browser workflow, start Next on port 3011 and use the lockfile-pinned
`playwright-core` package with an installed Chrome:

```powershell
node node_modules\next\dist\bin\next dev --hostname 127.0.0.1 --port 3011
$env:RAILPLAN_BROWSER_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
corepack pnpm test:ps1:browser
```

Set `RAILPLAN_UI_URL` for another URL. The browser suite intercepts PS1 HTTP calls and is
not database evidence. Disposable screenshots go to ignored
`.test-artifacts/ui-screenshots`, or to `RAILPLAN_SCREENSHOT_DIR` when explicitly set.

Ollama/Qwen is optional and is not part of parsing, feasibility, validation or scoring.
Operational publication, production authentication and the official validator remain
separate deployment work.
