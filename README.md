# RailPlan

## Scenario A/B/C track-access optimisation

The PS1 workspace supports Scenario A, B and C generation. Scenario B enforces planned completion dates and minimises `7 × excess access nights + 5 × ECLO nights`. Scenario C allows delay, limits capacity excess to one per location/week, enforces independent two-week Alpha/Beta ECLO windows, and minimises `priority-weighted overrun + 7 × excess + 5 × ECLO`. Choose **Local preview** for stateless Scenario B/C solves or **Saved optimisation** for PostgreSQL-backed immutable history. See [SCENARIO_C_RELEASE.md](SCENARIO_C_RELEASE.md).

`app.py` remains a frontend-only launcher; it does not start FastAPI. Internal validation is not official judge validation, and score verification remains internal only.


The official **PS1 dataset is now integrated**. Open **PS1 · Hackathon dataset**
in the app to inspect the organiser example or import its eight CSV files.
See [PS1_INTEGRATION.md](PS1_INTEGRATION.md) for setup, dataset semantics,
new APIs and PS1 integration. An **internal provisional submission validator**
now checks uploaded A/B/C schedules; see [PS1 validation](railplan-backend/docs/PS1_VALIDATION.md).
Database persistence requires `alembic upgrade head` (revision **0009**).
Validator 1.1.0 accepts the organiser sample with internal objective 48.30 and 70
unverifiable physical-alignment warnings. CSV feasibility is not physical-night clearance.
Judge validation has not run. Separate **Scenario A, B and C CP-SAT optimisers** generate
explicit-physical-night candidates and releases CSVs only after rich validation passes.
See [optimiser API, offline usage and limitations](railplan-backend/docs/PS1_OPTIMISATION.md).
Scores remain internal-only; a bounded feasible result is not necessarily optimal.

Optimiser POSTs now save immutable terminal runs, rich reports, physical assignments
and accepted CSVs, with idempotency and baseline references. See
[persistence design](railplan-backend/docs/PS1_OPTIMISATION_PERSISTENCE.md) and
[manual test guide](railplan-backend/docs/PS1_PERSISTENCE_TEST_GUIDE.md).
The Scenario A offline CLI and Scenario B/C previews remain database-free. The PS1 workspace exposes all three solvers; no operational publication workflow is added.

RailPlan is a rail-maintenance planning prototype with a Vinext/React interface and a FastAPI/PostgreSQL/PostGIS backend. This merged build includes persistent maintenance data, deterministic conflict detection, conflict severity scoring, and an analysis dialog connected to the backend.

## Included components

- `app/`: RailPlan planner interface
- `railplan-backend/app/`: FastAPI API, conflict engine, and scoring service
- `railplan-backend/migrations/`: one Alembic chain from `0001` through `0009`
- `railplan-backend/sql/`: schema, guards, views, scoring, history, and demo rules
- `railplan-backend/tests/`: API, rule-engine, scoring, and optional PostgreSQL tests
- `MERGE_GUIDE.md`: what was merged and why

The conflict engine checks schedule bounds, sector occupancy, spatial separation, isolation state, engineer/team/equipment double booking, availability, skills, equipment requirements, dependencies, and scenario travel time. Its results are explainable snapshots. It is a prototype and does not grant operational authority.

## Start the backend

Requirements: Python 3.11+, Docker, and Docker Compose.

```bash
cd railplan-backend
# Create your own .env using variables in railplan-backend/README.md.
# Environment files are intentionally excluded from the downloadable ZIP.
docker compose up -d db
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
set -a
source .env
set +a
alembic upgrade head
python -m app.seed
python -m app.seed_scoring
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API documentation is at `http://127.0.0.1:8000/docs`. The demo seed also installs the synthetic `CE-*` conflict rules. `app.seed_scoring` is optional.

## Start the frontend

In another terminal from the project root:

```bash
# Local defaults work; optional NEXT_PUBLIC_RAILPLAN_API_URL and
# NEXT_PUBLIC_RAILPLAN_DEMO_USER_ID can go in your own .env.local.
pnpm install --frozen-lockfile
pnpm dev
```

Open the local URL printed by Vite, normally `http://127.0.0.1:5173`. Select **Analyse conflicts**, connect to `http://127.0.0.1:8000`, and use the prefilled demo planner ID.

## Validate

```bash
cd railplan-backend
python -m pytest -q
```

PostgreSQL/PostGIS integration tests run only when `TEST_DATABASE_URL` points to a disposable database whose name starts with `railplan_test`.

From the project root:

```bash
pnpm exec tsc --noEmit
pnpm build
```

## API flow

1. `GET /api/engineering-windows`
2. `GET /api/command-centre/{window_id}`
3. `POST /api/analyses`
4. `GET /api/analyses/{analysis_id}`
5. `GET /api/analyses/{analysis_id}/conflicts`
6. Optional scoring through `/api/conflicts/{conflict_id}/scoring-context` and `/scores`

Generic non-PS1 optimisation, AI copilot, verified production authentication, and operational approval/publication services remain unavailable.

## Verify all four backend features

After starting the API and running both seed commands, open another terminal in
`railplan-backend`, activate the virtual environment, and run:

```bash
python -m scripts.verify_features
```

This checks database readiness, runs conflict detection through FastAPI, retrieves
saved conflicts, computes a five-component severity score, and retrieves the saved
score. It creates one analysis and one score in your local demo database.

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and set the
backend environment variables using the PowerShell example in
`railplan-backend/README.md`; the `source` commands above are for macOS/Linux.

Scoring is available through the API and backend TypeScript scoring adapter.
The frontend analysis dialog displays rule severity; numeric scoring is a separate
API operation requiring the demo scoring administrator or safety-reviewer role.
