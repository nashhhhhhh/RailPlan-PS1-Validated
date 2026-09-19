# RailPlan FastAPI backend — v0.4

## PS1 Scenario A/B/C

Scenario B and C are available through stateless previews and auditable saved-run endpoints. Both use deterministic CP-SAT, scaled workload integers, explicit physical nights, canonical footprints, and Validator 1.1.0's rich publication gate. Scenario B has hard planned-date completion; Scenario C balances priority-weighted delay, ECLO and capacity excess while enforcing the one-unit capacity ceiling and separate Alpha/Beta ECLO windows. Apply migration `0011` before saved optimisation. `/health` reports validator and Scenario A/B/C solver availability separately from database readiness.

Scenario A now has a separate OR-Tools CP-SAT optimiser with explicit physical nights,
locks, lexicographic objectives and a fail-closed rich-validation gate. Read
[PS1_OPTIMISATION.md](docs/PS1_OPTIMISATION.md) for API/offline use and limitations.
The HTTP endpoint now saves sealed terminal optimisation history; the pure solver/CLI
stays database-free. Migration head is **0011**. See
[persistence and transaction design](docs/PS1_OPTIMISATION_PERSISTENCE.md) and
[manual verification](docs/PS1_PERSISTENCE_TEST_GUIDE.md). No schedule is published.

New: deterministic conflict severity scoring, versioned policies, immutable evidence
history, stale-input/idempotency checks, and UI scoring adapters. See
[Conflict scoring setup and API workflow](docs/CONFLICT_SCORING.md). Run
`alembic upgrade head` to install migrations through **0011**, then optionally
`python -m app.seed_scoring` after the normal demo seed.

Prototype scores remain partial/unvalidated; blocking rules are never weakened.
Latest verification is recorded in [VALIDATION.md](docs/VALIDATION.md).
PS1 submission validation is separate from severity scoring: see
[PS1_VALIDATION.md](docs/PS1_VALIDATION.md) for rules and provisional assumptions.

This package extends the original PostgreSQL foundation with APIs for the existing RailPlan UI.
Start here, then read [the endpoint inventory](docs/API_ENDPOINTS.md) and [frontend integration](frontend/README.md).

## What is implemented

- Maintenance request listing, creation, draft editing, submission and cancellation
- Version checks and immutable submitted requested timings
- Manual scenario creation/cloning, preview and assignment editing
- Timing/team/engineer/equipment/sector lock enforcement and lock release
- Command centre, timeline, scenario comparison and change replay reads
- Network/GeoJSON and resource availability reads
- Deterministic conflict analysis, immutable evidence history, approval history and per-user activity reads
- Narrow CORS, scoped authorization, structured errors, correlation IDs and transactional audit events
- Typed TypeScript client, generated OpenAPI types and UI data adapters
- Additive Alembic revisions 0002–0011 and integration tests
- Stateless PS1 validation, immutable validation history and structured evidence

The project-root frontend now opens a backend analysis dialog from its conflict-analysis
control. UI colours, camera controls, animation and replay cursor remain frontend state.

## What remains unavailable

A background optimiser worker/queue, real AI copilot, verified OIDC adapter and
operational approval/publication are not implemented. PS1 Scenario A/B/C optimisation is
synchronous and bounded. Generic non-PS1 optimisation remains unavailable. Synthetic seed
scenarios remain clearly unvalidated UI presets.

## Local setup

Requires Python 3.11+, PostgreSQL 16/PostGIS (or Docker Compose), and an extension-capable
migration account. The provided owner account is for local development only.

1. Create your own `.env` containing `POSTGRES_PASSWORD` and the variables below.
   Match that password in `DATABASE_URL`. Environment files are excluded from the ZIP.
2. Run `docker compose up -d db`.
3. Run `python -m venv .venv` and activate it.
   - Windows: `.venv\Scripts\Activate.ps1`
   - macOS/Linux: `source .venv/bin/activate`
4. Run `python -m pip install -e ".[test]"`.
5. Set the environment variables below. Python does not load `.env` automatically.
6. Run `alembic upgrade head` to install the ordered migration chain through 0011.
7. Run `python -m app.seed` on a local demo database if synthetic fixtures and conflict rules are wanted.
8. Run `uvicorn app.main:app --reload --host 127.0.0.1`.
9. Open http://127.0.0.1:8000/docs.

PowerShell:

```powershell
$env:DATABASE_URL="postgresql+psycopg://railplan_owner:YOUR_PASSWORD@localhost:5432/railplan"
$env:RAILPLAN_ENV="development"
$env:RAILPLAN_DEMO_AUTH="1"
$env:RAILPLAN_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
```

POSIX shell:

```bash
export DATABASE_URL="postgresql+psycopg://railplan_owner:YOUR_PASSWORD@localhost:5432/railplan"
export RAILPLAN_ENV="development"
export RAILPLAN_DEMO_AUTH="1"
export RAILPLAN_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
```

Percent-encode reserved characters in URL passwords. Never commit secrets.

Print demo IDs:

```bash
python -c "from app.seed import uid; print('planner:',uid('planner')); print('window:',uid('window'))"
```

Pass the planner UUID as `X-Demo-User-Id`. This header is **local test identity, not authentication**.
It is rejected when RAILPLAN_ENV is not development or demo auth is not explicitly enabled.
A future bearer-token adapter must validate issuer, audience, signature, expiry and identity mapping;
the backend currently does not accept bearer tokens as proof of identity.

## Transactions and editing

Request handlers use synchronous sessions and function-scoped dependencies. Commit/rollback
finishes before returning a successful response. API mutations serialize per operator through
a PostgreSQL transaction advisory lock; this favours straightforward correctness for the pilot.

PATCHes require `expected_version`. Draft scenario content edits bump the scenario version
through existing triggers. A stale client receives 409 and must reload.
Request changes invalidate associated draft validations through migration 0002.

Submitted request timings never change through timeline dragging. Create a manual draft scenario
and change its assignments. Reviewed/approved scenario content remains frozen.

Locks retain owner, reason, scope, locked values, expiry and release history. Clone carries
source-specific locks forward. A possession-linked assignment cannot be edited in place by
this API; use a new manual draft for planning.

## Retry policy

The client performs **no automatic retries**.

- GETs can be retried.
- Activity-read and lock-release operations are idempotent.
- Versioned PATCH/submit/cancel retries usually receive 409 after the first commit; reload to reconcile.
- Create-request/create-scenario/clone operations do not yet have idempotency keys.
  After a network timeout, inspect server state before resubmitting; do not blindly retry.

## Data and response semantics

The original 89-table schema and SQLAlchemy mappings remain authoritative through migrations.
Read the [ER diagrams](docs/ERD.md) and [data dictionary](docs/DATA_DICTIONARY.md).

- UUIDs identify resources; MR/CF codes are display labels.
- Times are timezone-aware instants, rendered in Asia/Singapore by the client.
- Intervals use half-open bounds: adjacent jobs do not overlap without an additional buffer rule.
- Missing analysis returns NULL, not a false “zero conflicts” result.
- Conflict APIs require a particular analysis run; historical runs are not mixed together.
- Existing snapshots cannot prove freshness, so responses say `freshness: unknown`.
- Resource availability is calendar coverage, not full allocation feasibility. Candidates still
  need existing booking, crew-count, travel, roster and safety validation.
- No seed geometry is fabricated. NULL geometry returns an explicit unavailable flag.
  Bounding-box queries omit records with unknown geometry.
- Map responses are paginated GeoJSON Feature objects, not one unbounded FeatureCollection.
- Lists default to 50 records and cap at 200. Command-centre data has explicit caps and a
  `truncated` flag; use paginated endpoints to load the rest.
- Activity visibility is scoped through event actors' operator. Actor-less system events are
  withheld until an explicit operator-scoped system-event model is added.

## Tests

```bash
python -m pytest -q
```

Build-environment results: **181 Python tests passed; 36 PostgreSQL tests skipped**.
The frontend dependency install could not finish because this environment's offline cache
was missing one package tarball; run the TypeScript check and build after a normal install.

The skipped tests cover real migrations, triggers, request lifecycle, scenario edits/locks,
resource reads, event persistence, ownership isolation and rollback. No PostgreSQL server was
available here, so database-backed endpoints require those tests before deployment.

See [VALIDATION.md](docs/VALIDATION.md) for commands and exact limitations.

## Directory guide

| Location | Purpose |
|---|---|
| app/main.py | API composition, errors, CORS and health |
| app/dependencies.py | Identity, authorization and DB dependency |
| app/routers/requests.py | Request lifecycle, locks and releases |
| app/routers/scenarios.py | Manual scenarios, comparison, preview/edit |
| app/routers/network.py | Map and resource reads |
| app/routers/operations.py | Command centre, evidence, activity, capability boundaries |
| app/contracts.py | Public response and mutation models |
| app/schemas.py | Original request and integration inputs |
| app/repository.py | Scoped queries, versions and read helpers |
| app/services.py | Reused persistence services |
| app/conflict_engine.py | Deterministic rule evaluation and persistence |
| app/analysis_snapshot.py | One-statement input and evidence snapshot |
| app/worker_contracts.py | Future worker and copilot contracts |
| frontend/ | Typed client, adapters and tests |
| docs/openapi.json | Generated API specification |
| migrations/versions/0002_api_support.py | Additive API migration |
| migrations/versions/0003_conflict_scoring.py | Versioned conflict scoring |
| migrations/versions/0004_analysis_history.py | Immutable analysis history |

## Before operational deployment

Configure verified identity, least-privilege non-owner DB roles, complete operator isolation
tests, authoritative railway rules, a consistent versioned input graph, durable workers/outbox,
and validated approval/publication transactions. Add backup/restore, load and concurrency tests.

The API is not authorization for track access, electrical switching or worker deployment.
Do not expose the local demo identity adapter publicly.

Reference implementation patterns:
[FastAPI routers](https://fastapi.tiangolo.com/tutorial/bigger-applications/) and
[FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/).
