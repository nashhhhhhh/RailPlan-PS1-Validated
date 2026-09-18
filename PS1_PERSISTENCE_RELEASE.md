# PS1 optimiser-run persistence release

Built from `RailPlan-PS1-Scenario-A-Optimiser.zip`. This release saves immutable terminal
results and adds retrieval APIs; it does not deploy the application.

## Delivered

- Migration **0007** / SQL 010 and five dedicated PS1 tables, with ownership-consistent
  foreign keys, audited append-only rows, creation-transaction child guards and deferred
  complete-result sealing. No legacy optimisation tables or migrations are repurposed.
- Short READ COMMITTED transactions before/after computation. Commit succeeds before
  saved-success response; database failures propagate and roll back all related inserts.
- Original request, effective configuration, all solver/validation/policy versions,
  exact result/validation/diagnostic snapshots, accepted CSV strings and canonical rows.
- Operator+instance-scoped idempotency keys, normalized fingerprints, short final key
  lock/recheck and same-instance accepted baseline resolution. New keys allow new attempts.
- All terminal outcomes retained, including bounded UNKNOWN, rejected candidates and
  handled ERROR. Only accepted schedules appear in ordinary rows/artifact downloads.
- Additive POST response; history/detail/access/occupancy/artifact GET routes; typed client
  and generated contracts. The original OptimiseInput generated type remains available.
- Structured export bundle with compatible original wrapper. Pure solver/CLI unchanged.
- Tests, known-feasible small fixture generator and Bash/PowerShell manual verification.

## Files added

- `railplan-backend/app/ps1_optimisation/persistence.py`, `saved_contracts.py`
- `railplan-backend/app/ps1_optimisation_models.py`
- `railplan-backend/migrations/versions/0007_ps1_optimisation_runs.py`
- `railplan-backend/sql/010_ps1_optimisation_runs.sql`
- `railplan-backend/tests/test_ps1_optimisation_persistence.py`, `test_ps1_optimisation_postgres.py`
- `railplan-backend/scripts/create_ps1_smoke_fixture.py`
- `railplan-backend/docs/PS1_OPTIMISATION_PERSISTENCE.md`, `PS1_PERSISTENCE_TEST_GUIDE.md`
- `PS1_PERSISTENCE_RELEASE.md`

## Files updated

- Root `README.md`, `PS1_INTEGRATION.md`, historical `SCENARIO_A_RELEASE.md`
- Backend `README.md`, `app/main.py`, `app/ps1_optimisation/exporter.py`,
  `app/routers/ps1_optimisation.py`, `migrations/env.py`
- Backend tests `test_postgres.py`, `test_ps1_optimisation.py`, `test_static.py`
- Backend frontend `client.ts`, `client.test.cjs`, `contracts.generated.ts`
- Backend docs `openapi.json`, `API_ENDPOINTS.md`, `CONTINUATION_NOTES.md`,
  `DATA_DICTIONARY.md`, `ERD.md`, `PS1_OPTIMISATION.md`, `VALIDATION.md`

Organiser files, core solver/service/options, validator, pinned OR-Tools dependency and
frontend manifests/lockfile are byte-for-byte unchanged from the base ZIP.

## Verification and limits

Fresh checks: **436 Python/API tests passed, 91 skipped**; focused optimiser/persistence
suite **97 passed**; Node client **18 passed**; strict TypeScript and production build
passed; OpenAPI/types regenerated (**64 paths, 75 schemas**). No final test failures.

All 91 database checks were skipped: no safe rollback, committed or migration test URLs
were configured. Real migration upgrade, concurrency, fresh committed reload, SQL trigger
sealing and PostgreSQL rollback guarantees are therefore **unverified**, not passed.
SQL parsing and mocked boundary tests are not substitutes. Full commands, warning details
and exact skip categories are in `railplan-backend/docs/VALIDATION.md`.

Use `PS1_PERSISTENCE_TEST_GUIDE.md` before migration/testing. Alembic reads DATABASE_URL,
not TEST_DATABASE_URL. Separate disposable databases are required for rollback, committed
and migration suites. Committed test data is intentionally retained; no destructive
downgrade or cleanup is forced. The manual small fixture avoids a large public solve.

Terminal-only persistence cannot recover a process killed before commit. Concurrent
same-key requests may both compute but only one result can be saved under the key.
Wall-limited reruns can differ; stored snapshots reload exactly. Publishable means the
internal rich gate passed. Always `judge_validation="not_run"`,
`score_verification="internal_only"`; no official compatibility or operational approval.

No worker, queue, optimiser UI, scenario comparison/replay, approval/publication, B/C
optimisation or AI integration was added. Source-only archive excludes dependencies,
credentials, environment files, generated build output and caches.
