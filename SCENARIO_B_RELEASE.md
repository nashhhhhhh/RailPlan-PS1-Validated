# Scenario B optimiser release

RailPlan now generates Scenario B schedules with Google OR-Tools CP-SAT. This is an internal provisional implementation of the published PS1 rules; official judge validation was not run and all displayed scores are internal only.

## Model and objective

- Work is integer-scaled: normal access `2`, ECLO access `3`, required work `2 × total_accesses`.
- Every activity receives sufficient work, has at most one access per week, respects its planned start, and starts strictly after its predecessor's last access week.
- A contract's derived Sunday completion date may not exceed its planned completion date.
- Capacity use is the number of canonical `(location_id, week, co_share_group)` possessions. Scenario B permits excess.
- The primary objective is exactly `7 × excess_access_nights_total + 5 × eclo_nights_total`.
- Lexicographic tie-breaks minimise excess, ECLO, workload over-delivery, completion weeks, baseline movement, then a stable placement rank.

`physical_night`, `access_night`, and `co_share_group` remain separate identities. Physical nights are network-wide concurrency slots. Access nights are contract/type/week allocation indices. Co-share groups are location/week possession labels.

The CP-SAT model has optional access-presence, week, physical-night, local access-night and ECLO variables; activity/contract completion variables; possession-use and location/week excess variables; scaled delivered-work variables; baseline-movement flags; and a stable-rank tie-break. Hard constraints cover planned starts, continuous sequences, one access/activity/week, dependencies, local allocations, workfronts, possession mixes, canonical footprint conflicts, sufficient work and planned contract completion. In Scenario B, a legal co-share exempts common occupied locations only: it cannot erase buffer, opposite-bound or interchange conflicts elsewhere.

Week, physical night, local access night and ECLO can be locked. Co-share labels are deterministic export labels derived from location/week/physical-night concurrency, so a placement-level label lock is rejected instead of being silently ignored. Baselines are soft; movement counts changes in week, physical night, local night or ECLO. Scenario A baseline rows retain `eclo=0` and are never silently rewritten to ECLO.

## Interfaces and validation

- `POST /api/ps1/instances/{instance_id}/optimise/scenario-b` saves a terminal, immutable run in PostgreSQL.
- `POST /api/ps1/optimise/scenario-b/preview` accepts eight source CSV texts and creates no history, authentication state, or database records.
- `GET /api/ps1/instances/{instance_id}/optimisations?scenario=B` returns filtered history.

Both preview and saved optimisation require FastAPI. The root `app.py` launches only the frontend. Candidates pass rich validation with a complete explicit physical-night map. CSVs are released only when feasibility is true, physical validation is complete, and hard violations are empty.

## Bounded deterministic solving

Wall-clock and deterministic-time budgets are bounded, with one solver worker and a caller-supplied deterministic seed. A bounded feasible incumbent is labelled `FEASIBLE`; `OPTIMAL` is used only after every lexicographic stage is proven. A bounded run with no incumbent returns `UNKNOWN` and no accepted CSV artifacts.

## Provisional assumptions

No dated engineering-night calendar is provided. The versioned policy therefore uses a configurable uniform domain of 1–7 network-wide physical nights per week. Completion is Sunday of the final access week, matching Validator 1.1.0. Capacity supply counts canonical occupied possession groups, not buffer or mirrored-closure locations.
