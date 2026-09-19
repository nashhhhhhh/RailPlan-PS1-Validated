# Validation — merged FastAPI v0.4

## Current possession-closure verification (2026-09-19)

Policy 5 corrects the externally reported cross-group closure defect. Preprocessing now
retains 384 interacting pairs on the organiser instance (previous release report: 312),
and compatible access types are not treated as an exemption until the model assigns one
valid possession. Export grouping is fail-closed and the CSV validator independently
reconstructs group closures.

| Command / check | Actual result |
|---|---|
| `python -m pytest -q` | **490 passed, 100 skipped**, 0 failed; PostgreSQL/PostGIS URLs were not configured |
| Focused optimiser/validator/static tests | **241 passed**, 0 failed |
| Frozen pnpm install | Passed supply-chain policy check for **883** lockfile entries |
| Root strict TypeScript | Passed |
| Root PS1 client tests | **19 passed**, 0 failed |
| API client tests | **21 passed**, 0 failed |
| Vinext production build | Passed; plugin timing and route-classification notices only |
| Browser workflow | Not executed successfully: the Vinext dev server failed during startup with an internal runner error; the browser harness then correctly reported connection refused |
| Contract export | **75 paths, 80 schemas** |
| Organiser A (60 s) | `FEASIBLE`, score **202.30**, bound **25.20**, rich validation complete, zero violations |
| Organiser B (60 s) | `FEASIBLE`, score/bound **50.00**, rich validation complete, zero violations |
| Organiser C (120 s) | `FEASIBLE`, score **11070.30**, bound **18.20**, rich validation complete, zero violations |
| Independent final-CSV audit | A/B/C each passed with **0 cross-group closure intrusions** |

The solver runs are bounded feasible incumbents, not optimality claims. Exact output is in
`ORGANISER_CLOSURE_INVARIANT_RUN_20260919.json`; the separate auditor result is in
`ORGANISER_CLOSURE_AUDIT_20260919.json`. Judge validation remains `not_run` and scores
remain `internal_only`.

## Current Scenario C verification (2026-09-19)

| Command / check | Actual result |
|---|---|
| `python -m compileall -q app migrations tests scripts` | Passed |
| `python -m pytest -q` | **487 passed, 100 skipped**, 0 failed; one dependency deprecation warning |
| Focused A/B/C, validator, API/static and conflict tests | **306 passed**, 0 failed; included above |
| Scenario C module | **12 passed**, included above |
| PostgreSQL/PostGIS suites | **100 skipped** because `TEST_DATABASE_URL`, `TEST_COMMITTED_DATABASE_URL`, and `TEST_MIGRATION_DATABASE_URL` were not configured; no live migration/persistence claim |
| `python -m scripts.export_contracts` | **75 paths, 80 schemas** |
| API-client `npm test` | TypeScript build passed; **21 passed**, 0 failed |
| Root PS1 client tests | **19 passed**, 0 failed |
| Root strict typecheck | Passed |
| Next.js and Vinext production builds | Both passed |
| Browser workflow | **25 checks passed**, including stateless Scenario A preview |
| Official A/B/C generation, wall budget 120 s / deterministic budget 60 | A, B and C all `FEASIBLE`, rich-validation complete, zero hard violations; see `ORGANISER_RUN_RESULTS.json` |

The official judge was not run. `judge_validation` remains `not_run` and all scores remain
`internal_only`. The guarded PostgreSQL tests cover Scenario C ECLO windows, objective and physical
row retention, exact CSV retention, migration head 0011, the duplicate-trigger regression,
repeat upgrade and both seed commands, but they are among the skipped tests above.

## Previous optimiser-persistence verification

These checks were freshly executed for migration 0007 / saved optimiser-run APIs.
Historical solver/validator results below are not presented as fresh persistence evidence.

| Command / check | Actual result |
|---|---|
| `python -m pytest -q` (backend) | **436 passed, 91 skipped**, 0 failures; 2 dependency deprecation warnings |
| `python -m pytest tests/test_ps1_optimisation.py tests/test_ps1_optimisation_persistence.py -q` | **97 passed**, 0 failures; included above |
| `python -m pytest tests/test_postgres.py tests/test_ps1_optimisation_postgres.py -q -rs` | **91 skipped**: 56 existing rollback-database checks, 34 new committed-database checks, 1 separate migration check |
| `python -m pytest tests/test_static.py -q` | **41 passed**; SQL syntax parsing/model-column compilation, not PostgreSQL execution |
| `python -m scripts.export_contracts` | **64 paths, 75 schemas**, including the preserved `OptimiseInput` component |
| `node node_modules/typescript/bin/tsc --noEmit --strict` (root) | Passed |
| `npm test` (`railplan-backend/frontend`) | **18 passed**, 0 failed |
| `npm run build` (root) | Passed; existing proxy, plugin-timing, large-chunk and route-classification notices |
| Small synthetic PS1 smoke fixture | Importable and rich-validator-feasible; regression-tested without database |
| Original organiser sample | Existing CSV-only baseline regression passes; still no supplied physical mapping |
| Byte comparison with Scenario A source ZIP | Organiser inputs/references/samples, solver core/options/service, validator, dependency manifests and lockfile unchanged |

Commands used the existing Python virtual environment at
`/workspace/scratch/1aa0de0d7e76/ps1-venv/bin/python` and reused the installed frontend
dependency tree. A fresh frozen-pnpm install was not performed. Source ZIP excludes both
dependency trees. No new solver/dependency version was introduced.

**PostgreSQL is unverified in this environment.** `TEST_DATABASE_URL`,
`TEST_COMMITTED_DATABASE_URL` and `TEST_MIGRATION_DATABASE_URL` are not configured.
No live upgrade, database downgrade attempt, committed reload, concurrent-session race,
database trigger/audit/rollback or persisted artifact download was claimed as passed.
The Python downgrade function's deliberate refusal was unit-tested; that is not a live
database downgrade test. No SQLite replacement or unintended development DATABASE_URL
was used. New database tests have their own committed fixture; they do not pretend the
old rollback fixture's uncommitted schema is visible to another connection.

Executed unit/API-boundary checks cover normalized fingerprints, option defaults/order,
baseline conversion/ambiguity, invalid references, exact bundle/CSV agreement, metric
precision and primary-stage bound units, distinct outcome/optimality flags, no database
transaction during computation, success only after commit, handled errors, diagnostic-only
candidate retention, idempotent early reuse/collision and artifact rejection. Mocked
transaction tests do not prove PostgreSQL guarantees. The committed tests additionally
cover sealing, later child insertion, mutation/TRUNCATE denial, real key races, rollback
including key/audit/event, fresh connection reads, exact snapshots, ownership and paging.

No test failures remain. Known non-failing warnings are Starlette/httpx and AnyIO test-client
deprecations, npm proxy configuration, Vite chunks over 500 kB and Vinext static route
classification/plugin timings. Browser interaction, production identity, live PostgreSQL,
concurrent load, dated engineering-night calendars and official judge validation remain
unverified. No new large public-instance quality/optimality claim is made this release.

Read [persistence design](PS1_OPTIMISATION_PERSISTENCE.md) and
[Bash/PowerShell manual test guide](PS1_PERSISTENCE_TEST_GUIDE.md) before database verification.

## Previous Scenario A optimiser verification

Verified with OR-Tools 9.14.6206, validator 1.1.0 and explicit-night policy version 2:

| Check | Result |
|---|---|
| Complete Python/API suite | **394 passed, 56 skipped**, 0 failures; 2 existing dependency deprecation warnings |
| Focused optimiser tests | **56 passed**, included in the complete suite |
| PostgreSQL tests | **56 skipped**, no `TEST_DATABASE_URL`; no live PostgreSQL assertions claimed |
| OpenAPI / TypeScript export | **59 paths, 70 schemas**, regenerated |
| Strict root TypeScript | Passed |
| Node client tests | **16 passed**, 0 failed |
| Frontend production build | Passed; existing bundle-size, route-classification, proxy and plugin-timing notices |
| Public dataset offline solve, default 20-second budget | **FEASIBLE**, rich validation passed; 54 activities / 192 accesses / 14 contracts; no hard violations |
| That public run's objective | **4944.10 internal weighted overrun**, 161 raw contract-overrun days; zero ECLO/excess; primary optimum **not proven** |
| Original organiser sample | Unchanged; CSV-only feasible, score **48.30**, 70 alignment warnings; no physical mapping supplied |
| Official judge | **Not run**, all scores internal-only |

The public run used seven physical nights/week, seed 0, deterministic budget 10 and
single-worker CP-SAT. It stopped after approximately 20.13 seconds of solve time with
scaled incumbent 49441 and lower bound 252 (unscaled 25.20). This is a feasible starting
candidate with a large optimality gap, **not a high-quality or optimal schedule claim**.
An earlier 20-second run reached 4969.30; wall-clock stopping explains different
incumbents despite the same seed. Fixed-seed stable output is tested on completed small
solves; deterministic-work budgeting with wall headroom is needed for repeatable cutoffs.
The sample's 48.30 is not a rich-validated benchmark and is never presented as generated output.

One initial optimiser test failed because a three-activity fixture used the inherited
workfront limit of two and insufficient supply to complete nine accesses in four weeks.
The fixture now explicitly supplies three workfronts; no scheduling rule was weakened.
Final checks have no failures. OR-Tools installation initially retried a proxy timeout,
then succeeded using the configured connection. Frontend checks reuse the pre-existing
dependency tree; a clean frozen-pnpm installation is not verified. Python dependencies
add the pinned solver; frontend package manifests/lockfile are unchanged.

New tests cover full workload/ECLO, planned starts and dependency failure, every possession
mix, both buffer boundaries, buffer-only overlap, opposite/interchange closures, local
allocation/workfront limits, group supply counting, night identity independence, locks,
baseline tie-break ordering, canonical occupancy/results, exact objective weights,
deterministic table-order independence, bounds/invalid placements, bounded public status,
fail-closed validation, CLI export/no-overwrite, API roles/errors and typed client use.
Two additional PostgreSQL tests cover same-operator read-only computation and cross-operator
and viewer rejection; they remain skipped alongside the existing database suite.

Browser interaction, live PostgreSQL/PostGIS, production authentication, concurrent load,
dated physical engineering calendars and official-validator comparison remain unverified.
That historical Scenario A release made no optimiser UI, persistence or operational approval claim. See
[PS1_OPTIMISATION.md](PS1_OPTIMISATION.md) for all assumptions and model limits.

The sections below describe historical verification of the preserved validator.

## Previous PS1 validator verification

Verified for `ps1-validator/1.1.0`:

| Check | Result |
|---|---|
| Python `python -m pytest -q` | **338 passed, 54 skipped**, 2 dependency deprecation warnings |
| PostgreSQL integration tests | **Not run**: no safe `TEST_DATABASE_URL` configured; all 54 skipped |
| Root `npx tsc --noEmit --strict` | Passed |
| Root `npm run build` | Passed; existing >500 kB bundle-size warning and framework route-classification notice |
| Existing Node client `npm test` | **15 passed**, 0 failed |
| OpenAPI / generated TypeScript contracts | Regenerated: **58 paths, 67 schemas** |
| Organiser sample | **CSV-feasible: zero hard violations, 70 alignment warnings, internal score 48.30**; physical-night alignment not verified |
| Official validator | Not supplied / not run; all scores internal |

Verification reused the existing Python virtual environment and installed frontend dependency
tree from the merged project; no dependencies or lockfiles were changed. The default Python
initially lacked pytest; the full suite passed when run using the existing virtual environment.
Frontend build also reports proxy environment and plugin-timing notices. No test failures.
A frozen pnpm installation, browser interaction,
PostgreSQL execution and concurrent load testing remain unverified. All eight input files
and three organiser sample files remain unmodified. Details: [PS1_VALIDATION.md](PS1_VALIDATION.md).

The following sections describe historical checks from earlier merged releases.

## Executed

- **181 Python checks passed**.
- **36 real PostgreSQL/PostGIS integration checks skipped** because no database server/TEST_DATABASE_URL is available.
- Frontend dependency installation could not finish in this environment because
  one package tarball was absent from its offline package cache. TypeScript and
  browser build validation remain required in a normal networked development environment.
- Python source compilation passed.
- OpenAPI regenerated from the merged application with conflict-analysis routes.

Scoring checks cover weight validation, Decimal rounding, severity thresholds,
fixed-denominator partial scores, unknown data, confidence separation, blocking,
pairwise overlap, physical resource identity, scenario input handling, role gates,
concurrency-token validation, migration SQL parsing and nullable UI bars.
Database score persistence, immutable history, idempotency, activation and rollback
tests are included in the skipped integration suite. Live multi-connection
concurrency testing is outstanding. No backend or UI deployment was performed.

Python tests cover SQL parsing, ORM/schema parity, seed references, Pydantic rules, structured
errors, authorization boundaries, worker unavailability, route ordering, query bounds,
generated parameterized read SQL, basic preview rules, all five lock field types, stale
versions, cross-midnight intervals, readiness error sanitization, and CORS restrictions.

Client tests cover timezone conversion, timeline offsets, repeated comparison parameters,
AbortSignal propagation, no automatic retry/mock fallback, malformed responses, rejected
previews preventing writes, and reloading after edits.

The HTTP unit tests use dependency overrides. They do **not** prove PostgreSQL execution.
SQL parsing does not type-check database objects or execute PL/pgSQL trigger bodies.

Two deprecation warnings originate in the installed FastAPI/Starlette test client dependencies.
They do not affect the recorded pass count.

## Database integration suite

Requires an empty disposable PostgreSQL 16/PostGIS database. The name must start with
railplan_test and it must not already contain a railplan schema.

Create it with the local Compose service:

```bash
docker compose exec db createdb -U railplan_owner railplan_test
```

PowerShell:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://railplan_owner:YOUR_PASSWORD@localhost:5432/railplan_test"
python -m pytest tests/test_postgres.py -v
```

POSIX:

```bash
export TEST_DATABASE_URL="postgresql+psycopg://railplan_owner:YOUR_PASSWORD@localhost:5432/railplan_test"
python -m pytest tests/test_postgres.py -v
```

The fixture installs the original SQL assets plus migrations through 0004 inside a transaction,
loads synthetic seeds, and rolls back at completion. Each test uses a savepoint.
No existing schema is dropped.

Database tests include:

- PostgreSQL/PostGIS version, idempotent seeds, range adjacency and spatial intersection
- Resource overlap candidates, isolation and dependency queries
- Missing/expired qualifications
- Original request and audit immutability
- Scenario history/freeze and command-centre query
- SQLAlchemy/database column parity
- Lock snapshot persistence
- HTTP request creation → patch → stale rejection → submit → cancel
- Scenario preview without mutation, lock rejection, release and successful edit
- Unknown geometry and unknown availability
- Per-user activity read state
- Invalid-reference rollback
- Cross-operator access isolation

## Reproduce non-database checks

```bash
python -m pytest tests/test_static.py tests/test_api.py -q
python -m compileall -q app migrations scripts tests
cd frontend
npm install
npm test
```

## Still required before deployment

A live database pass, clean-environment install, actual frontend wiring/browser verification,
OIDC integration, least-privilege DB roles, concurrency/load tests, backup/restore tests and
complete domain validation remain outstanding.

No API service was deployed or connected to the hosted frontend. No real railway data,
operational approval or schedule publication was used.
