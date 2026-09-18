# RailPlan PS1 optimiser UI integration release

Built from `RailPlan-PS1-Optimiser-Persistence.zip`. This release connects the existing Vinext/React PS1 workspace to the persistent Scenario A FastAPI API. It does not deploy the application or change the optimiser, validator, persistence schema or organiser dataset.

## Delivered

- Saved-instance prerequisite and direct route to the existing save control.
- Scenario A configuration for time limits, deterministic limit, seed and physical nights.
- Synchronous solve state with honest indeterminate feedback and browser-wait cancellation semantics.
- Frozen idempotent retries after transport failures and a new UUID for intentional attempts.
- Saved run history, terminal status, optimality, bound/gap, validation trust labels and diagnostics.
- Complete paginated access and occupancy loading at 200 rows per request with partial-response rejection.
- Week × network-wide physical-night timeline with filters, density control and selected-access inspector.
- Location/week-scoped occupancy inspector and Alpha/Beta network highlighting.
- Contract completion, priority-weighted overrun and baseline-change views.
- Soft saved-run baselines and hard access-placement locks for the next solve.
- Exact stored CSV downloads; unavailable artifacts remain explicit on rejected runs.
- Responsive tablet layout, keyboard tab navigation, visible focus states, reduced-motion support and non-colour status cues.
- Scenario B/C generate actions remain disabled because only Scenario A optimisation exists.

## Files added

- `app/ps1-optimisation-panel.tsx`
- `app/ps1-optimisation-data.ts`
- `app/ps1-optimisation.css`
- `tests/ps1-optimisation.test.cjs`
- `tests/ps1-optimisation.browser.cjs`
- `docs/PS1_UI_INTEGRATION.md`
- `docs/ui-screenshots/*.png`
- `PS1_UI_RELEASE.md`

## Files updated

- `app/ps1-workspace.tsx`
- `package.json`

No backend Python, migration, SQL, generated contract or organiser input file was changed.

## Verification

- New PS1 data/integration checks: **16 passed, 0 failed**.
- Mock-API browser flow: **17 checks passed**. It covered save prerequisite, Scenario A request shape, demo-user header, B/C blocking, all-page loading, activity highlighting, baseline and lock payloads, internal trust labels, artifact 409, byte-exact CSV download, UNKNOWN handling, exact retry, stale-response protection, browser reload, idempotency collision recovery and tablet rendering.
- Existing typed API client: **18 passed, 0 failed**.
- Existing Python/API suite: **436 passed, 91 skipped, 0 failed** with two dependency deprecation warnings.
- Strict TypeScript: passed.
- Production build: passed. The build reports an existing large-chunk advisory.

All 91 Python skips are PostgreSQL integration checks because `TEST_DATABASE_URL`, `TEST_COMMITTED_DATABASE_URL` and `TEST_MIGRATION_DATABASE_URL` were not configured. The browser test uses explicit intercepted responses and is UI evidence, not live database evidence. Run the existing `railplan-backend/docs/PS1_PERSISTENCE_TEST_GUIDE.md` against three fresh disposable PostgreSQL databases before treating persistence as fully verified.

## Trust boundaries

- `physical_night` is presented as the network-wide scheduling slot.
- `access_night` remains local to its allocation pool.
- `co_share_group` remains local to location and week.
- FEASIBLE and OPTIMAL remain separate states.
- Publishable means the internal rich-validation gate accepted the schedule.
- Judge validation remains `not_run`; score verification remains `internal_only`.
- Browser cancellation stops waiting only; the server can still finish and persist the synchronous run.
- The PS1 Alpha/Beta network is displayed schematically and never placed on the Singapore geographic map.
