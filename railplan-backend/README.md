# RailPlan FastAPI backend

The backend exposes maintenance-planning APIs, deterministic conflict analysis and
scoring, PS1 source-data ingestion, A/B/C submission validation, a Scenario A CP-SAT
optimiser, immutable optimiser history, and operator-scoped asynchronous Scenario A jobs.
The migration head is **0009**.

The optimiser and rich validator use explicit physical-night assignments. Accepted CSVs
are stored only after the rich validation gate passes. UNKNOWN, INFEASIBLE, MODEL_INVALID,
VALIDATION_FAILED and handled ERROR outcomes remain diagnostic records without published
CSV artifacts. Judge validation is not run and scores are internal only.

## Database-free development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`GET /health/ready` reports stateless readiness. These routes do not need PostgreSQL or
authentication:

- `POST /api/ps1/preview`
- `POST /api/ps1/validate`
- `POST /api/ps1/optimise/scenario-a/preview`

The offline Scenario A command is also database-free:

```powershell
.venv\Scripts\python -m app.ps1_optimisation --output ..\scenario-a-output
```

## Persisted development

Use the project-root `python app.py --persisted --seed` launcher, or start PostGIS and then:

```powershell
$env:DATABASE_URL="postgresql+psycopg://railplan_owner:ENCODED_PASSWORD@127.0.0.1:5432/railplan"
$env:RAILPLAN_ENV="development"
$env:RAILPLAN_DEMO_AUTH="1"
$env:RAILPLAN_CORS_ORIGINS="http://127.0.0.1:5173"
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m app.seed
.venv\Scripts\python -m app.seed_scoring
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Pass the seeded planner UUID as `X-Demo-User-Id`. This header is a local development
identity and is rejected outside development. Production must use a verified identity
adapter. Never commit credentials or environment files.

## Asynchronous optimisation jobs

`POST /api/ps1/instances/{id}/optimise/scenario-a/jobs` creates or safely reuses a durable
job record. Poll `/api/ps1/optimisation-jobs/{job_id}` and request cancellation at
`/api/ps1/optimisation-jobs/{job_id}/cancel`. Progress and state transitions are guarded
and audited by migrations 0008–0009. The bounded executor is in-process; deploy one API
replica or replace the adapter with a durable queue before horizontal scaling.

The original synchronous saved-run endpoint remains available. Both paths retain the
deterministic seed and bounded wall/deterministic solver limits.

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

Real database tests require `TEST_DATABASE_URL`, `TEST_MIGRATION_DATABASE_URL` and
`TEST_COMMITTED_DATABASE_URL`, each naming a disposable database beginning with
`railplan_test`. They apply migrations 0001–0009 and cover audit guards, immutability,
operator isolation, idempotency, rollback and concurrency. Tests skip explicitly when
these URLs are absent.

See [API_ENDPOINTS.md](docs/API_ENDPOINTS.md), [PS1_VALIDATION.md](docs/PS1_VALIDATION.md),
[PS1_OPTIMISATION.md](docs/PS1_OPTIMISATION.md),
[PS1_OPTIMISATION_PERSISTENCE.md](docs/PS1_OPTIMISATION_PERSISTENCE.md), and
[DEPLOYMENT.md](docs/DEPLOYMENT.md).

Ollama/Qwen integration is optional and outside feasibility and validation. Operational
approval/publication and official judge validation remain external responsibilities.
