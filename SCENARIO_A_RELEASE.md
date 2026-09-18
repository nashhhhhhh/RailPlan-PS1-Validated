# Scenario A source release

**Historical solver-release notes.** The current package also includes migration-0007
terminal persistence. Read `PS1_PERSISTENCE_RELEASE.md` for current changes and verification.

Built on RailPlan-PS1-Validated-1.1.0. Existing importer, validator 1.1.0, rule policy,
database migrations and organiser files are preserved. Source package excludes installed
dependencies, generated build output, caches, secrets and environment files.

## Delivered

OR-Tools CP-SAT Scenario A model; explicit network-wide physical nights distinct from
contract-local access indices and location-local possession groups; complete workload,
canonical occupancy, capacity/mixes, closures/buffers, allocations/workfronts, starts,
dependencies and locks. Exact scaled weighted-overrun objective with staged secondary
objectives. Organiser CSV exporter, fail-closed rich-validation gate, scoped API,
typed client and offline CLI. No optimisation UI, database history, approval or publishing.

## Files added

- `railplan-backend/app/ps1_optimisation/__init__.py`
- `railplan-backend/app/ps1_optimisation/contracts.py`
- `railplan-backend/app/ps1_optimisation/preprocessing.py`
- `railplan-backend/app/ps1_optimisation/scenario_a.py`
- `railplan-backend/app/ps1_optimisation/exporter.py`
- `railplan-backend/app/ps1_optimisation/service.py`
- `railplan-backend/app/ps1_optimisation/__main__.py`
- `railplan-backend/app/routers/ps1_optimisation.py`
- `railplan-backend/tests/test_ps1_optimisation.py`
- `railplan-backend/docs/PS1_OPTIMISATION.md`
- `SCENARIO_A_RELEASE.md`

## Existing files changed

- `README.md`, `PS1_INTEGRATION.md`, `railplan-backend/README.md`
- `railplan-backend/app/main.py`, `railplan-backend/pyproject.toml`
- `railplan-backend/tests/test_postgres.py`
- `railplan-backend/frontend/client.ts`, `client.test.cjs`, `contracts.generated.ts`
- `railplan-backend/docs/openapi.json`, `API_ENDPOINTS.md`, `CONTINUATION_NOTES.md`,
  `DATA_DICTIONARY.md`, `ERD.md`, `PS1_VALIDATION.md`, `VALIDATION.md`

## Verification and limitations

- Complete Python/API suite: **394 passed, 56 skipped**, no final failures.
- Focused optimiser suite: **56 passed** (included above).
- PostgreSQL suite: **56 skipped** because no safe `TEST_DATABASE_URL` is configured.
- Strict TypeScript and production build passed. Node client suite: **16 passed**.
- OpenAPI/types regenerated: **59 paths, 70 schemas**. Python dependency check passed.
- Public instance: 54 activities / 192 accesses / 14 contracts generated and rich-validated,
  zero hard violations, no ECLO or capacity excess. Default 20-second run returned FEASIBLE,
  internal objective **4944.10**, raw contract overrun **161 days**; optimum not proven.
- Organiser sample unchanged: CSV-only feasible, internal 48.30 and 70 alignment warnings;
  it is not a generated solution or a physically verified comparison benchmark.
- All organiser input, reference and sample bytes match the source archive.

Physical availability assumes up to seven configured night slots each week, not a dated
operator engineering calendar. Fixed-seed completed solves are repeatable; wall-limited
incumbents can differ under load. Official geometry/alignment/scoring conventions still
need comparison with the unavailable judge validator. All results retain
`judge_validation="not_run"`, `score_verification="internal_only"`.

See `railplan-backend/docs/PS1_OPTIMISATION.md` for model, API, bounds and assumptions,
and `railplan-backend/docs/VALIDATION.md` for exact verification results, initial corrected
fixture failure, dependency/build notices and skipped checks. PostgreSQL, clean frozen
pnpm install, browser interaction and concurrent-load verification remain outstanding.

## Run offline

```bash
cd railplan-backend
python -m pip install -e ".[test]"
python -m app.ps1_optimisation --output /tmp/railplan-scenario-a-new
```

Output directory must be new. Successful internal validation writes report JSON plus
the three CSVs. Preserve the report's physical-night mapping with those CSVs.
