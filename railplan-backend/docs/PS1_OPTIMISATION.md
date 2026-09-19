# Scenario A/B/C optimiser — internal, validation-gated

## Scenario C

Scenario C reuses the elastic Scenario B core but replaces the hard completion deadline with the official balanced score. Normal access contributes 2 scaled workload units, ECLO contributes 3, and each activity requires `2 × total_accesses`; surplus is allowed and minimised only after the official objective. Capacity uses distinct canonical location/week possession groups and enforces `excess <= 1` for every location/week.

The model computes activity overrun with the validator's Sunday completion conversion. Its exact scale-10 weighted term is `tier_weight × activity_multiplier_scaled_10 × activity_overrun_days`, summed by activity, where tier weights are 100/10/1 and multipliers are 13/12/10. The primary integer objective is `weighted_overrun_scaled_10 + 70×excess + 50×ECLO`; dividing by 10 exactly reproduces `priority_weighted_overrun + 7×excess + 5×ECLO`.

Alpha and Beta have independent active/start/end variables. Every ECLO access whose canonical closure footprint affects a line is included in that line's min/max used week, with `end-start <= 1`. An ECLO access affecting both lines therefore satisfies both windows without merging unrelated one-line windows. The result retains active state, exact start/end, contributing activities and cross-line ECLO activity IDs.

Scenario C stages are: official score, weighted overrun, excess, ECLO, raw contract overrun, workload over-delivery, completion weeks, baseline movement and stable rank. Each proven stage is fixed before the next; a time-limited incumbent is reported as feasible-bounded, never optimal. Generated files pass through `validate(..., "C", physical_nights=mapping)` and are withheld unless rich validation is fully complete and feasible.

## Scenario B

Scenario B uses optional access rows with scaled work `normal=2`, `ECLO=3`, `required=2×total_accesses`. It enforces planned starts, dependencies, weekly allocation, workfronts, legal possession mixes, canonical closures/buffers, sufficient workload, and contract completion on or before the planned date. Supply excess is legal and summed across canonical location/week possession groups.

Stages are official score (`7×excess + 5×ECLO`), excess, ECLO, workload over-delivery, completion weeks, baseline movement, and stable rank. A time-limited feasible primary stage is never labeled optimal. The physical-night domain remains provisional because the official package contains no dated night calendar.

`ps1-optimiser/1.2.0` uses pinned Google OR-Tools **9.14.6206** CP-SAT and
`ps1-validator/1.1.0`, policy `ps1-policy/4-scenario-c-line-windows`. No LLM,
legacy nightly conflict engine or 0–100 severity score participates. Organiser
inputs and sample files are unchanged; the sample is never used as a solver hint.

## Three night identities

| Identity | Scope | Purpose |
|---|---|---|
| `physical_night` | Network-wide within a week | Internal concurrent possessions, closures, buffers and workfronts. `(week, physical_night)` identifies a night. |
| `access_night` | Contract + activity type + week | Allocation and workfront index, exported in ACCESS. |
| `co_share_group` | Location + week | One legal possession and one supply unit, exported in OCCUPANCY. |

The physical domain is explicitly configured as **1–7 slots/week**, default **7**,
never inferred from a contract's 2/3-night allowance. Weekly supply quantities do
not specify dated engineering-night availability. The model assumes configured slots
are available network-wide each week, subject to location supply; they are internal
engineering-night assignments, not verified bookings on an operator's real calendar.

For each contract/type/week, every used physical night receives a distinct local index
in `1..number_of_maximum_access_per_week`. Its concurrent activities share that index
and consume workfronts together. Different contracts can use local index 1 on different
physical nights. This meaningful alignment is stronger than CSV-only information.

All activities at one location/week/physical night form one legal possession.
Local labels `g001`, `g002`, … enumerate that location/week's used physical nights.
Matching labels elsewhere never establish concurrency. Physical nights are never
reconstructed from either local indices or group labels.

## Modules, variables and hard constraints

`contracts.py` bounds input/output. `preprocessing.py` calls existing canonical
`network.chains/expand` and computes incompatible pairs. `scenario_a.py` builds/solves
CP-SAT. `exporter.py` derives CSVs and tuple-key mapping. `service.py` independently
validates the candidate. The scoped route now saves terminal results through the separate
[persistence layer](PS1_OPTIMISATION_PERSISTENCE.md); pure optimisation remains database-free.

Variables include access week `W[a,k]`, physical night `N[a,k]`, local night `L[a,k]`;
presence `x[a,w,n]` and `p[a,w]`; sequence/week selectors; weekly night/local channels;
contract/type/night used flags and local labels; location/week/night possession flags;
activity and contract completion weeks; activity and contract overrun days; baseline
movement flags. Unique negative sentinels distinguish unused local labels under
`AllDifferent`. Possession flags are the OR of canonical occupied presences and define
group membership, without arbitrary independent group-ID decision variables.

Enforced constraints:

1. Exactly `total_accesses` standard units for every activity; no ECLO variable and
   every export has `eclo=0`. Continuous access sequences have strictly increasing weeks;
   at most one access per activity/week (not an obligation to work every horizon week).
2. Planned-start weeks; successor first week strictly after predecessor final week.
   Horizon is fixed and never silently extended to hide infeasibility.
3. Full canonical platform/tunnel occupancy, including book-in and book-out. Number of
   occupied possession groups per location/week is at most fixed supply; zero excess.
4. PM alone, one PC plus at most three C, or at most four C. Every location's entire
   group must be legal. Sharing reduces supply use but never workload.
5. Same-physical-night non-overlap only for precomputed incompatible footprint pairs.
   Collision families use occupied/buffer/opposite/interchange/closure exactly as the
   validator, including buffer-buffer intersections. Potential legal sharing at every
   common occupied location exempts a pair; full-group mix constraints still apply.
6. Live two-sector buffers; Consist one; Others none; clip to line ends. Live alone
   mirrors the expanded closure and crosses H01/H02. Non-live lines and bounds retain
   separate capacities. Buffers/mirrors alone do not consume occupied-location supply.
7. Contract/type/week distinct used nights respect allocation. Concurrent activities
   of that contract/type on each local/physical night respect workfronts.
8. Locks fix access week and physical night, plus local index if supplied. Partial locks
   are supported; lock every sequence to fix an entire activity. Baseline placements
   are soft preferences, not locks. Contradictions produce infeasibility, never relaxation.

Rule-family and lock assumptions yield a sufficient, not necessarily minimal,
infeasibility core. Structural channeling constraints remain active. Pair diagnostics
retain activity IDs, collision kinds and locations. UNKNOWN means the solve budget
ended without an incumbent; it is not proof that any constraint is impossible.

## Objective and reproducibility

Completion is Sunday: `horizon_start + 7*completion_week - 1 day`. Activity overrun is
`max(0, completion_date - contract/type planned_completion_date)`. Primary score sums
activity overrun times contract tier **100/10/1** times activity multiplier **1.3/1.2/1.0**.
CP-SAT uses exact scale-10 integers: `tier * {13,12,10} * overrun_days`. Independent
validation uses Decimal and HALF_UP to two decimals. Raw overrun counts each contract
once. Scenario A has no ECLO or excess penalties.

Lexicographic stages:

1. Scaled weighted overrun.
2. Raw contract overrun days.
3. Sum of activity and contract completion weeks.
4. Number of baseline access placements moved in week, physical night or supplied local
   index. Locked placements cannot move, so their movement is always zero.
5. Stable sorted placement-rank sum with deterministic integer coefficients. This is
   a tie-break, not a claim of a mathematically unique canonical solution.

Only a proven OPTIMAL stage is fixed before starting the next. No secondary objective
can sacrifice even one scaled primary unit. A FEASIBLE stage stops staging. If a later
stage has no incumbent before timeout, retain the earlier candidate. `primary_optimal`
and `lexicographic_complete` are separate; top-level OPTIMAL requires all stages complete.

Sorted variable construction/exports, one worker, default seed 0. Wall solve budget
0.1–120 seconds (default 20) and deterministic work budget 0.001–60 (default 10) are
shared across all stages. Model build and validation are outside solve time; build time
is reported separately. Gates cap 200 activities, 2,000 accesses, 50,000 presence slots,
60,000 sequence/week slots, 300,000 pair/night constraints and 20,000 occupancy rows.

With fixed version, seed and deterministic stopping point, search/output is reproducible.
**Wall-clock cutoff may yield different incumbents across machines or under load.** Use
a deterministic work limit with sufficient wall headroom when repeatability matters.
Timing fields are telemetry, not deterministic output. Bounded FEASIBLE is not proven
optimal. Production queueing, rate limits, cancellation propagation and load tests remain
future work. The HTTP endpoint now uses short transactions before and after computation;
no database transaction is held across solving.

## Validation gate and exports

Every candidate goes through:

```python
validate(dataset, submission_files, "A", physical_nights=physical_night_mapping)
```

`publishable:true` requires `feasible:true`, `physical_validation_complete:true`, and
zero hard violations. Publishable means internal gate passed, not approval or judge
acceptance. Solver failure yields no CSVs. Gate failure nulls top-level files/placements
and retains the rejected candidate only as `failed_candidate` with `diagnostic_only:true`.

Exact headers:

```text
SCHEDULE_ACCESS.csv: activity_id,access_seq,week,eclo,access_night
SCHEDULE_OCCUPANCY.csv: activity_id,week,location_id,co_share_group
RESULTS.csv: scenario,contract_number,simulated_completion_date,overrun_days
```

Python retains `{(activity_id, week): physical_night}`. JSON has a sorted `physical_nights`
placement array including sequence and local index. Preserve it beside the CSVs: CSV-only
re-upload loses physical alignment. RESULTS derives one completion/overrun per contract.
Complete baselines get activity/contract completion deltas; partial baselines have null
deltas. Explanations describe derivation, not an unperformed causal sensitivity analysis.

## API and offline use

Install: `python -m pip install -e ".[test]"`. Migration head is **0011** for saved HTTP runs.

`POST /api/ps1/instances/{instance_id}/optimise/scenario-a` requires same-operator
planner/administrator. Existing identity, transaction and error envelopes apply.

```json
{
  "time_limit_seconds": 20,
  "deterministic_time_limit": 10,
  "random_seed": 0,
  "physical_nights_per_week": 7,
  "locked_placements": [],
  "baseline_placements": []
}
```

Placement fields: `activity_id`, `access_seq`, `week`, `physical_night`, optional
`access_night` and Scenario B/C `eclo`. Possession labels are derived from physical-night
concurrency and cannot be locked directly. Unknown, duplicate or out-of-domain placements return HTTP 422. Other
operator/missing instance: 404; wrong role: 403. Bounded/infeasible solves return HTTP 200
with status, not transport failure. Existing 10 MB wire limit applies.

Response includes solver status, `candidate_source`, `optimality_proven`, publishable/lexicographic flags, solve time, stage values
and bounds, settings/policy, objective components, three CSV strings, explicit assignments,
rich report, completion changes and diagnostics. Always `judge_validation:"not_run"`
and `score_verification:"internal_only"`. Typed client:
`RailPlanClient.optimisePs1ScenarioA(instanceId, options, signal)`,
`optimisePs1ScenarioB(...)`, and `previewPs1ScenarioB(...)`.

The PS1 workspace exposes Scenario A/B/C generation while preserving the existing style. All three scenarios have stateless preview routes; the saved routes retain immutable history and the UI compares the latest A/B/C results while warning that their formulas differ. Legacy generic optimiser capability remains false and does not describe these PS1 routes. Dedicated immutable
optimisation history now retains rich results and physical assignments; see
[persistence APIs](PS1_OPTIMISATION_PERSISTENCE.md) for additive request/response fields.
There is no approval/publication write. Do not store rich results via the CSV-only
validation-history endpoint, which would lose physical alignment.

Offline, without PostgreSQL or authentication:

```bash
cd railplan-backend
python -m app.ps1_optimisation --output /tmp/railplan-new-scenario-a
# Optional: --input /path/to/eight-csvs --options /path/to/options.json
```

Output directory must not exist. It receives `report.json` and, only on a passing gate,
three CSVs. Exit 0 means internally publishable; exit 2 means bounded/failed.

## Official-comparison assumptions

Official validator is unavailable. Compare engineering-night availability/calendars,
local-to-physical alignment, partial-span sharing exemption, buffer endpoints and
buffer-triggered interchange closure, mirrored platforms, closure-only supply, Sunday
completion, strict later-week dependencies, fixed horizon and README prose versus explicit
weighted formula. No official compatibility, operational authority or global optimality
claim. Organiser sample remains a reference, not a RailPlan-generated schedule.

See [verification](VALIDATION.md) for exact checks and public-run status. Integer arithmetic
and CP-SAT statuses follow [Google's documentation](https://developers.google.com/optimization/cp/cp_solver).
