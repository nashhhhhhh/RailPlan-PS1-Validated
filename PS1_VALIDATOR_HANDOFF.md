# PS1 submission validator handoff

Implemented `ps1-validator/1.1.0`, validation only. No optimiser, AI,
severity scoring or legacy nightly detector determines PS1 feasibility.

## Files changed / added

New backend package `railplan-backend/app/ps1_validation/`:
`__init__.py`, `contracts.py`, `submission.py`, `network.py`, `rules.py`, `scoring.py`,
`service.py`, `persistence.py`.

New routes: `railplan-backend/app/routers/ps1_validations.py`.
Updated application registration, body limits and readiness: `railplan-backend/app/main.py`.
Updated ORM inventory: `railplan-backend/app/ps1_models.py`.
New migration `railplan-backend/migrations/versions/0006_ps1_validations.py` and
`railplan-backend/sql/009_ps1_validations.sql`.

Frontend: updated `app/ps1-workspace.tsx` and `app/ps1.css`; new `app/ps1-validation-panel.tsx`.
Tests: new `railplan-backend/tests/test_ps1_validation.py`; updated `test_postgres.py`
and `test_static.py` in the same directory.

Generated artifacts: `railplan-backend/docs/openapi.json` and
`railplan-backend/frontend/contracts.generated.ts`.
Documentation: root `README.md`, `PS1_INTEGRATION.md`, this handoff;
`railplan-backend/README.md`; backend docs `PS1_VALIDATION.md`, `VALIDATION.md`,
`API_ENDPOINTS.md`, `ERD.md`, `DATA_DICTIONARY.md`, `CONTINUATION_NOTES.md`.
Packaging: new `scripts/package-source.py`.

All supplied input CSVs, sample outputs and source PS1 README remain unchanged.

## Implemented rules

All 21 requested families: schema, unknown_reference, duplicate, workload,
access_sequence, weekly_activity_access, planned_start, dependency, occupancy,
possession_mix, closure, buffer, live_opposite_bound, live_interchange, capacity,
weekly_allocation, workfront, eclo, eclo_window, planned_date, results_consistency.

Canonical expansion includes every tunnel and book-in/intermediate/book-out platform;
Live/Consist buffers clip at boundaries; Live-only mirrors/crossover are explicit.
Legal sharing consumes one slot but retains activity workload. Local night budgets and
workfronts, scenario supply limits, ECLO arithmetic/windows, result reconciliation and
Decimal A/B/C objectives are separate, deterministic steps. Any hard violation nulls the
eligible objective while retaining diagnostic metrics and structured evidence.

## Verification

- Python: **338 passed, 54 skipped**, 2 dependency deprecation warnings.
- PostgreSQL: **not run**; all 54 database tests skipped without `TEST_DATABASE_URL`.
- TypeScript strict check: **passed**.
- Production build: **passed**, with large-bundle warning and route-classification notice.
- Existing Node client tests: **15 passed**, 0 failed.
- OpenAPI: regenerated **58 paths and 67 schemas**, plus TypeScript contracts.
- Browser interaction and frozen pnpm installation were not tested. npm dependency
  installation completed without lifecycle scripts and without changing the pnpm lockfile.

## Does the organiser sample pass?

**Yes, under CSV-only validation.** All 54 activities and 192 units are complete;
all 14 result summaries match. There are **70 alignment warnings**, zero hard violations,
and internal objective **48.30**. Raw overrun is 28 days, excess supply and ECLO are zero.
This does not prove physical safety: `physical_validation_complete` is false.

Python `validate` accepts optional `physical_nights={(activity_id, week): night_id}`.
Rich schedules are checked by week/night/location. Complete positive-integer assignments
are required; missing, extra or malformed keys and possession groups split over nights
fail closed. Distinct explicit same-night possessions collide even if their local labels
differ. Legal sharing is preserved. Local access indices and labels are never globally
matched. Rich fingerprints include sorted assignments. Existing HTTP routes stay CSV-only.
Policy: `ps1-policy/2-explicit-night-alignment`. UI and JSON distinguish both contexts.

The organiser README calls this same sample feasible. The official validator was not
provided and was not run. Do not claim judge parity or an officially verified objective.

## Assumptions requiring official comparison

Cross-location possession-night alignment; partial-span co-sharing exemption; buffer
endpoints and buffer-only intersections; buffer-triggered interchange closure; exact
opposite/cross-line platform closure extent; closure versus supply consumption; week-end
completion versus earliest workload delivery; same-week dependency ordering; ECLO count
aggregation; multi-type contract date consistency; and activity-level weighted versus
contract-level raw overrun aggregation. All active assumptions are in each report.

## Next steps

Run migration 0006 against your local database, then the PostgreSQL tests using an empty
disposable `railplan_test...` database. Compare the sample and targeted mutations with
the official validator before revising policy. Only then build a separate optimiser.
No production deployment or operational approval is included.

The ZIP excludes dependencies, build output, caches, credentials and environment files.
Create your own environment configuration following the updated READMEs.
