# API follow-up fixes

Scenario B generation, stateless preview, saved persistence, filtered history, UI mode selection, migration `0008`, and regenerated contracts are implemented. Scenario C generation remains intentionally disabled. The uniform 1–7 physical-night domain and Sunday completion conversion remain versioned provisional assumptions pending official clarification.

## PS1 terminal optimiser persistence (current)

- Migration 0007 / sql/010; five dedicated immutable tables with same-transaction child
  insertion, canonical manifest checks and deferred complete-result sealing at commit.
- POST preserves existing top-level result fields and adds run ID/created/reused metadata.
  Dedicated short READ COMMITTED transactions close before solving and commit before reply.
- Key identity is operator+instance+key; normalized input hash includes versions/settings,
  sorted locks/resolved baseline. Same key reuses any terminal outcome; new keys can re-solve.
- Final advisory key lock/recheck handles races; duplicate solves may occur, duplicate saved
  results under the same key may not. Never catch database failures as solver errors.
- Baseline references require same operator/instance and accepted rows. No external candidate
  ingestion. Rich gate is preserved; rejected candidates stay diagnostic-only.
- API/client retrieval and canonical export bundle are added. Pure solver/CLI unchanged.
- `PS1_OPTIMISATION_PERSISTENCE.md` and `PS1_PERSISTENCE_TEST_GUIDE.md` contain schema,
  transaction, metric, manual-test and environment details. `VALIDATION.md` has current totals.
- Real PostgreSQL commit/concurrency and live migration verification are unexecuted without
  explicit disposable test URLs. Never substitute SQLite or historical passing notes.
- Production identity, queue/cancellation, UI, comparison, replay and official judge parity
  remain future work. Process termination before final commit has no terminal record.

## Scenario A optimiser 1.0.0 (original release notes)

- `app/ps1_optimisation/`: bounded single-worker CP-SAT, full standard workload,
  distinct physical/local/group identities, canonical footprints, locks and baselines.
- Scoped compute-only API and offline CLI. No migration, history or approval write.
- Scale-10 primary score and staged secondary objectives; no primary-score sacrifice.
- Every exported candidate passes unchanged validator 1.1.0 with explicit physical nights.
  Preserve the report mapping alongside CSVs; do not save it as CSV-only validation history.
- Pinned OR-Tools 9.14.6206; generated API contracts and typed client updated.
- Public instance can yield a rich-feasible bounded incumbent, not necessarily optimal.
- See PS1_OPTIMISATION.md and VALIDATION.md for bounds, assumptions and exact checks.
- Follow-up: official comparison, PostgreSQL verification, dated engineering calendars,
  optimisation persistence if requested, UI controls, production load/cancellation handling.
  B/C optimisation and operational approval remain out of scope.

## PS1 validator 1.1.0 (preserved)

- Pure implementation: `app/ps1_validation/`; API: `app/routers/ps1_validations.py`.
- Migration 0006 / `sql/009_ps1_validations.sql` follows immutable-instance migration 0005.
- No AI, solver, nightly-model conversion or severity-score reuse.
- UI: existing workspace plus `app/ps1-validation-panel.tsx` (upload, validation,
  saved history, metrics, filters/highlights and JSON download).
- Public sample: 54 workloads complete, 192 accesses, RESULTS match; 70 alignment
  warnings, zero hard violations, internal objective 48.30.
- Python validate accepts optional physical_nights; CSV-only feasibility is not
  physical-night clearance. Explicit mapping validation fails closed if incomplete.
- Obtain the official validator before resolving alignment/completion assumptions.
  Version policy changes; never rewrite old immutable runs.
- API/rules/limits: `PS1_VALIDATION.md`; latest checks: `VALIDATION.md`.
- PostgreSQL execution, browser interaction and concurrent load remain unverified.
  Earlier totals below are historical.

## v0.3 scoring

- Scoring engine: app/scoring.py; transactional routes: app/routers/scoring.py.
- Migration 0003 installs sql/005_scoring.sql; four additive models in app/scoring_models.py.
- Demo scoring policy/admin seed is separate and works after existing demo data.
- frontend/scoring.ts supplies scoring client and UI panel adapter; site unchanged.
- OpenAPI/types regenerated with scripts/export_contracts.py.
- 132 Python checks and 15 Node checks passed; 35 DB checks skipped without TEST_DATABASE_URL.
- Current factors/policies are prototype-only, partial/unvalidated; passenger evidence is absent.
- Source revision is intentionally conservative and database-wide; production throughput and
  multi-connection concurrency require validation. See CONFLICT_SCORING.md for the full contract.

## Prior v0.2 fixes

- Fixed-time request intent is enforced during scenario preview/edit even without a separate lock.
- Cloned scenarios do not copy locks for requests omitted from the clone.
- Original active timelines omit cancelled/rejected/completed requests; explicit scenario history remains available.
- Framework-generated 404/405 errors now use the same error envelope as domain errors, preserving Allow headers.
- Singapore date/time input rejects invalid calendar rollovers such as February 30 and 24:00.
- Timeline adapters reject invalid original positions and non-positive intervals.
- Client error handling accepts a null error body without crashing.
- Added typed client methods for reference data, map data, resources, availability, run status and approval history.

Verification: 90 Python checks and 12 client tests pass. The 28 real PostgreSQL/PostGIS tests
remain unexecuted in this environment. Read docs/VALIDATION.md to run them locally.

The original UI is unchanged. Copy the three TypeScript files in frontend/ and connect the
existing React data handlers following frontend/README.md. No backend was deployed.
