# Deployment

`Dockerfile` builds the FastAPI service. `docker-entrypoint.sh` applies Alembic migrations
before starting Uvicorn when `RAILPLAN_RUN_MIGRATIONS=1`. `compose.prod.yaml` runs the API
with PostgreSQL 16/PostGIS 3.5 and a named persistent volume.

## Required environment

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Initial database-owner password used only by the database container. |
| `DATABASE_URL` | Percent-encoded SQLAlchemy URL reachable from the API container, normally `postgresql+psycopg://railplan_owner:ENCODED_PASSWORD@db:5432/railplan`. |
| `RAILPLAN_CORS_ORIGINS` | Comma-separated exact HTTPS frontend origins. Wildcards are rejected. |

Optional variables:

| Variable | Default | Purpose |
|---|---:|---|
| `RAILPLAN_BIND_ADDRESS` | `127.0.0.1` | Host interface used for the published API port. |
| `RAILPLAN_API_PORT` | `8000` | Published API port. |
| `RAILPLAN_API_WORKERS` | `1` | Uvicorn worker count. Keep 1 while using the in-process optimisation executor. |
| `RAILPLAN_OPTIMISER_WORKERS` | `1` | Bounded in-process optimiser worker count, maximum 4. |
| `RAILPLAN_RUN_MIGRATIONS` | `1` | Apply migration head before API startup. |

`RAILPLAN_ENV=production`, `RAILPLAN_DEMO_AUTH=0`, and
`RAILPLAN_REQUIRE_DATABASE=1` are set by the production compose file. Do not place secrets
in Compose YAML, Git, images, environment files inside the repository, or frontend build
variables. Use the deployment platform's secret store.

## Start

From `railplan-backend`:

```powershell
$env:POSTGRES_PASSWORD="database-owner-secret"
$env:DATABASE_URL="postgresql+psycopg://railplan_owner:database-owner-secret@db:5432/railplan"
$env:RAILPLAN_CORS_ORIGINS="https://railplan.example"
docker compose -f compose.prod.yaml up --build -d
```

Percent-encode reserved characters in `DATABASE_URL`. The database health check uses
`pg_isready`; the API readiness check calls `/health/ready`, which verifies database
connectivity and migration head `0009`. `/health` is the liveness endpoint.

## Limitations before production use

- The asynchronous executor is process-local. Use one API replica, or replace it with a
  durable external queue that retains the same database/HTTP state contract.
- A process restart leaves QUEUED/RUNNING job rows as diagnostic evidence; automatic lease
  recovery and requeue are not implemented.
- Production identity integration is not included. Demo identity is disabled.
- Backups, restore drills, monitoring, TLS termination, official rules/calendars, the
  official validator, and operational approval remain deployment responsibilities.
- The frontend is built separately; `compose.prod.yaml` deploys the API and PostGIS only.
