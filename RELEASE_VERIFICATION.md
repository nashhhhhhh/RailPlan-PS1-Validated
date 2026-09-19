# RailPlan release verification

Verified on 2026-09-19 in the supplied Windows workspace. This report separates executed
evidence from checks that the machine could not run.

## Release outcome

The database-free dashboard, FastAPI service, Scenario A preview, rich validator, existing
synchronous persistence contract, new asynchronous job contract, generated API artifacts,
typed clients and production frontend build pass their available checks. The one-command
stateless launcher returned HTTP 200 from the dashboard, `/health` and `/health/ready`.

This host has no Docker, PostgreSQL/PostGIS server, `postgres`, `psql` or Podman. Therefore
no honest disposable database could be created, and migrations 0001–0011 plus database
trigger/concurrency tests were **not executed against PostgreSQL**. SQL assets parse, the
Alembic chain resolves to head 0011, ORM/schema inventory checks pass, and the database
tests are retained for a suitably equipped release runner.

## Exact test evidence

| Check | Result |
|---|---|
| Complete Python suite | **469 passed, 96 skipped, 0 failed**, 2 dependency deprecation warnings, 23.62 s |
| PostgreSQL-only selection | **96 skipped** across rollback, committed-database and clean-migration fixtures |
| Root frontend client tests | **16 passed, 0 failed** |
| Generated backend TypeScript client tests | **21 passed, 0 failed** |
| Strict TypeScript (`tsc --noEmit`, strict project config) | Passed |
| Browser workflow | **17 checks passed** using installed Chrome and mocked PS1 HTTP boundaries |
| Production Vinext build | Passed all five build phases; emitted only Vinext's route-classification notice |
| Clean dependency install | `pnpm install --frozen-lockfile` passed after removing the prior `node_modules` tree |
| Stateless launcher smoke | Dashboard 200; FastAPI health 200; stateless readiness 200 |
| OpenAPI/contracts | Regenerated and parsed: **73 paths, 80 schemas**, API version 0.5.0 |
| Alembic graph | `0001 -> ... -> 0011 (head)` |

The 96 skipped PostgreSQL tests cover clean migrations, PostGIS/schema behavior, immutable
instances, persisted validation and optimiser runs, audit/sealing triggers, operator
isolation, idempotency collisions and deduplication, rollback, concurrent requests, job
progress/cancellation and destructive-downgrade refusal. They skipped because the three
required disposable `railplan_test*` database URLs were absent. No SQLite or mock database
was reported as equivalent evidence.

## Organiser dataset exercise

The checked-in [machine-readable result](railplan-backend/docs/ORGANISER_RUN_RESULTS.json)
was produced by `scripts/run_release_scenarios.py` with seed 0, a 20-second wall limit and
a 10-unit deterministic limit per scenario.

| Scenario | Source availability | Result | Elapsed | Objective bound/value | Physical validation | CSV policy |
|---|---|---|---:|---|---|---|
| A | Available | `FEASIBLE` | 22.484 s total; 20.109 s solve | bound 252, incumbent 16926; internal score 1692.60 | Feasible, complete, **0 violations** | Rich-validator-accepted CSVs retained in memory; none written to the source tree |
| B | Available | `FEASIBLE` | 22.969 s total; 19.390 s solve | bound 30, incumbent 253; internal score 253.00 | Feasible, complete, **0 violations** | Rich-validator-accepted CSVs retained in memory; none written to the source tree |
| C | Available | `UNKNOWN` | 16.968 s total; 13.360 s solve | bound 182, no incumbent | Not complete; **0 reported violations** because no candidate existed | No CSV generated or written |

The elapsed wall time includes about five seconds of deterministic model preparation in
addition to the configured CP-SAT solve budget. All entries retain
`judge_validation="not_run"` and `score_verification="internal_only"`. The organiser's
sample submission files remain reference material and were not relabelled as RailPlan output.

## Functional changes

- Added database-free `POST /api/ps1/optimise/scenario-a/preview`, reusing the existing
  Scenario A solver and explicit physical-night rich-validation gate.
- Integrated the existing Scenario B and C optimisers, stateless previews and saved-run
  endpoints without changing their documented solver rules.
- Added migrations 0010–0011 for operator-scoped durable optimisation jobs, guarded
  transitions, monotonic progress, audit history, idempotency and cancellation.
- Added asynchronous Scenario A start/list/poll/cancel APIs. Terminal solver evidence is
  stored through the existing sealed-run path; unsuccessful candidates expose no CSVs.
- Added `python app.py` stateless launcher and `--persisted` mode that starts PostGIS only
  when requested and applies migrations before serving.
- Added backend Dockerfile, migration entrypoint, production Compose, named PostGIS
  storage, liveness/readiness checks and environment documentation.
- Regenerated OpenAPI and TypeScript contracts; extended the typed client and tests.
- Updated the database dictionary, ERD, API inventory, persistence guide and UI guide.
- Pinned `playwright-core`, moved screenshots to disposable artifacts, and moved required
  Vite plugin source from `build/` to `tooling/` so all actual build output is removable.
- Removed tracked logs and 14 generated screenshots. Source packaging excludes dependency
  trees, build output, caches, logs, screenshots, environment files, secrets, database
  volumes and nested ZIPs.

## Files changed

Core/runtime:

- `.gitignore`, `README.md`, `app.py`, `package.json`, `pnpm-lock.yaml`, `vite.config.ts`
- `tooling/sites-vite-plugin.ts`, `tooling/sites-vite-plugin.LICENSE` (moved from `build/`)
- `railplan-backend/app/main.py`
- `railplan-backend/app/routers/ps1_optimisation.py`
- `railplan-backend/app/ps1_optimisation/{contracts,jobs,persistence,saved_contracts}.py`
- `railplan-backend/app/ps1_optimisation_models.py`
- `railplan-backend/sql/013_ps1_optimisation_jobs.sql`
- `railplan-backend/sql/014_ps1_optimisation_job_guards.sql`
- `railplan-backend/migrations/versions/0010_ps1_optimisation_jobs.py`
- `railplan-backend/migrations/versions/0011_ps1_optimisation_job_guards.py`
- `railplan-backend/scripts/run_release_scenarios.py`, `scripts/package-source.py`

Deployment/generated clients:

- `railplan-backend/{Dockerfile,.dockerignore,compose.prod.yaml,docker-entrypoint.sh}`
- `railplan-backend/docs/openapi.json`
- `railplan-backend/frontend/{client.ts,client.test.cjs,contracts.generated.ts}`
- `tests/ps1-optimisation.browser.cjs`

Tests:

- `railplan-backend/tests/test_{api,conflict_engine,postgres,ps1_optimisation,ps1_optimisation_persistence,ps1_optimisation_postgres,static}.py`

Documentation:

- `PS1_INTEGRATION.md`, `PS1_PERSISTENCE_RELEASE.md`, `SCENARIO_A_RELEASE.md`
- `railplan-backend/README.md`
- `docs/PS1_UI_INTEGRATION.md`
- `railplan-backend/docs/{API_ENDPOINTS,CONTINUATION_NOTES,DATA_DICTIONARY,DEPLOYMENT,ERD,PS1_OPTIMISATION,PS1_OPTIMISATION_PERSISTENCE,PS1_PERSISTENCE_TEST_GUIDE,VALIDATION}.md`
- `railplan-backend/docs/ORGANISER_RUN_RESULTS.json`, this report
- removed `docs/ui-screenshots/*.png` and `logs/*.png`

## Remaining provisional assumptions

- `physical_night` 1..7 is a network-wide weekly slot because no authoritative dated
  engineering-night calendar was supplied.
- `access_night` is local to contract/activity-type/week; `co_share_group` is local to
  location/week. Neither creates global alignment.
- Buffer extent, opposite-bound mirroring, live interchange propagation, closure-only
  capacity treatment, Sunday completion, strict later-week dependencies and the internal
  priority weighting remain policy interpretations pending organiser confirmation.
- AI/Ollama/Qwen is optional and contributes nothing to feasibility or validation.

## Known official-validator differences

The official judge/validator was not supplied or run. RailPlan's internal validator uses
explicit physical-night assignments to resolve concurrency that the three submission CSV
schemas cannot express. It reports the documented internal score and rich feasibility but
does not claim judge score parity, official acceptance, engineering-calendar validity or
operational authority.

## Deployment limitations

- Docker image/Compose execution was not tested on this host because Docker is absent.
- PostgreSQL/PostGIS migrations and database tests must run in CI or a release host before
  deployment; the exact disposable-database commands are in the persistence test guide.
- The job executor is in-process. Use one API replica, or replace it with a durable queue;
  restart recovery/requeue is not implemented.
- Production identity, official calendars/rules, official validation, backups/restore,
  monitoring, TLS termination and operational approval/publication remain external work.
- The production Compose file deploys FastAPI and PostGIS; the frontend is built/deployed
  separately.
