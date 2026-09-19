# Immutable PS1 optimiser-run persistence

## Scenario B/C additive persistence

Migration `0008` expanded the sealed run scenario check to `A/B` and the child access ECLO check to `0/1`. Migration `0009` additively expands the scenario check to `A/B/C`; it changes no rows or sealing/audit/immutability triggers and intentionally refuses downgrade. Scenario-specific fingerprints include scenario and objective policy, preventing A/B/C collisions. Result JSON retains workload, ECLO, Scenario C line windows and cross-line activities, excess, objective stages, hotspots, physical nights, validation, diagnostics, and exact accepted CSV text.

The original persistence release added terminal history to the synchronous Scenario A endpoint;
Scenario B and C use the same transaction boundary and sealed evidence model. Pure optimiser
version `ps1-optimiser/1.3.0`, validator 1.2.0, explicit-possession-closure policy 5, the
Scenario A offline CLI and organiser CSV schemas remain database-independent. Historical
migration **0007** follows **0006**, while current head is **0011**. None reuses legacy nightly
`optimisation_runs`, scenarios or CSV-only PS1 validation history.

## Transaction ownership and terminal lifecycle

The POST uses its own session factory, with **READ COMMITTED** isolation. It does not
receive the existing shared `DB`/`Actor` dependency transaction or call commit inside it.

1. A short read transaction calls the existing identity function, checks planner/admin,
   loads the same-operator instance, resolves baseline, validates references and computes
   effective input identity. If the key exists, matching input returns its saved result;
   different input returns 409. Close the transaction/session before solving.
2. Run the existing pure optimiser and rich-validation gate without a database session.
   Build canonical child records from the same exporter data as the exact CSVs.
3. Open a short writing transaction. Recheck identity, active role and instance ownership.
   Identity resets transaction-local actor/source/correlation audit settings. Take a
   scoped advisory key lock if a key is present, then recheck under READ COMMITTED.
4. If another request already committed that key, return its result after checking the
   fingerprint. Otherwise insert the run, accepted child rows, key and activity event.
   Commit evaluates deferred completeness checks; return success only after commit.

Database read/insert/commit exceptions are never swallowed. They use existing error
envelopes and roll back all new inserts, audit rows and activity events. The POST never
returns a saved/publishable success if persistence fails. Computation exceptions derived
from `Exception` are separately handled as terminal ERROR with sanitized diagnostics and
server-side logging. Invalid options/references are 422, with no run. Process exit or native
termination during synchronous execution can occur before a terminal run is recorded. The
asynchronous route added in migrations 0010–0011 records queued, running,
cancellation-requested and terminal state separately; restart recovery is not automatic.

Concurrent identical-key requests can both solve before either saves. The final key lock,
recheck and unique constraint guarantee **one committed result per scoped key, not one
solver execution**. A new key or no key intentionally starts a new attempt even when
the fingerprint matches. Stored snapshots reload exactly; rerunning a wall-limited solve
may produce a different incumbent.

## Schema and sealing

| Table | Contents / key |
|---|---|
| `ps1_optimisation_runs` | UUID; operator, immutable instance, creator, optional baseline; exact solver status/outcome; all versions/fingerprints; original parsed request (including which fields were supplied), effective configuration; complete result/validation/diagnostic JSONB; distinct optimality/physical/accepted flags; exact numeric metrics; solve time and start/completion/creation times; accepted CSV text; canonical schedule manifest; creating transaction ID. |
| `ps1_optimisation_accesses` | `(run_id, activity_id, access_seq)`; unique `(run_id, activity_id, week)`; physical night, local night, ECLO=0/1, lock indicator, optional baseline week/night. |
| `ps1_optimisation_occupancies` | `(run_id, activity_id, week, location_id)`; co-share group; FK to an access of the same activity/week. |
| `ps1_optimisation_contract_results` | `(run_id, contract_number)`; completion date and raw overrun. Optional weighted overrun is deliberately NULL; exact weighted activity components remain in the validation snapshot. |
| `ps1_optimisation_keys` | `(operator_id, instance_id, idempotency_key)`; run and input fingerprint. |
| `ps1_optimisation_jobs` | Operator-scoped queued/running/cancelled/terminal control record with immutable request identity, optional terminal run link and diagnostic JSON. Lifecycle changes are guarded and audited. |

Composite FKs prevent cross-instance/operator children, baselines and key references.
Creator membership and accepted baseline eligibility are checked on parent insertion.
History indexes use operator/instance/creation time/ID; child indexes support run/week,
activity and location filtering. Numeric scores/bounds/gaps use PostgreSQL NUMERIC and
Python Decimal; API summaries/detail render these metrics as strings to retain precision.

All five tables reject UPDATE, DELETE and TRUNCATE. A BEFORE INSERT trigger stamps the
parent's actual `txid_current()` regardless of caller input. Child/key insertion requires
the same creating transaction, so a previously committed run cannot acquire later rows.
Accepted children must already appear exactly in the parent's canonical manifest. This
also prevents extra rows after an early `SET CONSTRAINTS ... IMMEDIATE`. Key text must
match the original request. A deferred parent constraint trigger checks the entire child
sets/counts against the manifest at commit, metadata/snapshot consistency, accepted rich
validation/CSV retention and required key association. Missing children abort the result.

The manifest is intentional redundancy supporting database-enforced completeness, not
a replacement for validation. Audit insert triggers support composite-key children and
record the run as the audit entity. No mutable finalisation flag or weakened legacy
immutability rule is introduced. These guards apply to ordinary database users, not an
administrator who disables triggers or drops schema objects. Downgrade deliberately raises;
use an explicit archive/recovery process, not forced destructive rollback.

## Fingerprints, baselines and metrics

SHA-256 covers instance ID, dataset fingerprint, Scenario A, optimiser/validator/policy
versions and full policy snapshot, objective-policy identity, effective OR-Tools version,
fixed worker/night/alignment/stage settings, all effective options after defaults, sorted
locks, sorted resolved baseline placements and referenced baseline run ID. Keys, times,
telemetry and outputs are excluded. Absent and explicit-null local placement indices have
the same meaning; explicit numeric local indices change the hash. No unsupported
availability-calendar fields are invented.

`SavedOptimiseInput` extends `OptimiseInput` only for the HTTP persistence API:
`baseline_run_id?: UUID`, `idempotency_key?: 1..128 non-whitespace characters`.
The pure solver/CLI does not accept these database-only fields. A baseline reference must
be same operator, same instance and internally accepted. Its saved access rows convert
directly to `Placement` values retaining sequence/week/physical/local night. A reference
plus nonempty explicit baseline placements is 422; baseline is soft, locks are hard.

| Solver status | Terminal outcome | Meaning |
|---|---|---|
| OPTIMAL | optimal | All existing lexicographic stages completed optimally; accepted only if the rich gate passes. |
| FEASIBLE | feasible | Valid incumbent, possibly at a limit; optimality flags remain separate. |
| INFEASIBLE | infeasible | Infeasibility result/preflight proof, no accepted schedule. |
| UNKNOWN | bounded | No incumbent before limits; **not** proof of infeasibility. |
| MODEL_LIMIT | model_limit | Resource gate exceeded. |
| MODEL_INVALID | model_invalid | CP-SAT rejected the model. |
| VALIDATION_FAILED | validation_failed | Candidate rejected by rich validation; diagnostic artefact only. |
| ERROR | error | Handled computation exception. |

`primary_optimal` and `lexicographic_complete` are not collapsed. Objective score is the
accepted validator's exact score; otherwise NULL. Only the stage named
`weighted_overrun_scaled_10`, with FEASIBLE/OPTIMAL status and a finite nonnegative bound,
can supply a primary bound. Divide that bound by Decimal 10. Never use a later stage's
bound. Missing/invalid bounds remain NULL. Relative gap is
`(score - bound) / max(abs(score), 1)`, rounded HALF_UP to 12 decimals, as a fraction,
not percent. No accepted score means no gap; raw solver stage data remains unmodified.

## Trusted gate, canonical records and rejected candidates

The exporter now offers `export_bundle`, containing access/occupancy/contract records,
exact CSVs and the Python tuple-key physical mapping. Existing `export` still returns
`(files, mapping)`. Both use the same canonical construction; the solver is unchanged.
Persistence rebuilds that bundle from trusted placements and requires exact CSV equality.
It reuses the complete rich report already produced by the trusted service. No endpoint
accepts externally supplied candidates or a client-supplied publishable flag.

Accepted means the service's publishable flag, feasible rich report, complete physical
validation and zero hard violations all agree. Only accepted runs get ordinary schedule
rows and downloadable CSVs. Rejected candidates stay in `failed_candidate` with
`diagnostic_only:true`, in the saved result/detail only. Do not use the CSV-only validation
history route to store these results: it would lose physical-night alignment.

Physical assignments persist directly as placement objects and relational columns,
never JSON tuple keys. Physical night remains network/week-wide, access index remains
contract/type/week-local, and possession label remains location/week-local.
`judge_validation="not_run"`, `score_verification="internal_only"` always remain.
Publishable describes the internal gate, not operational authority or official acceptance.

## API and client

| Endpoint | Response / access |
|---|---|
| POST `/api/ps1/instances/{id}/optimise/scenario-{a,b,c}` | Existing top-level OptimiseResult plus `run_id`, `created`, `reused`, `created_at`, `terminal_outcome`, `input_fingerprint`; planner/admin. |
| GET `/api/ps1/instances/{id}/optimisations` | Lightweight paginated summaries, newest first; optional `scenario=A|B|C`. |
| GET `/api/ps1/optimisations/{run_id}` | `run` metadata/request/configuration; exact `result`, `validation`, `diagnostics`, ordered `contract_results`. |
| GET `/api/ps1/optimisations/{run_id}/accesses` | Paginated rows ordered week/activity/sequence; optional week and activity_id. |
| GET `/api/ps1/optimisations/{run_id}/occupancies` | Paginated rows ordered week/location/activity; optional week, activity_id, location_id. |
| GET `/api/ps1/optimisations/{run_id}/artifacts` | Exact saved filename-to-CSV-text `files` plus internal validation labels; 409 if visible run has no accepted files. |
| POST `/api/ps1/instances/{id}/optimise/scenario-{a,b,c}/jobs` | Create or reuse an asynchronous A, B or C job; returns 202 with durable status. |
| GET `/api/ps1/instances/{id}/optimisation-jobs` | Paginated job history for the same operator instance. |
| GET `/api/ps1/optimisation-jobs/{job_id}` | Poll status, progress, stage, diagnostics and terminal run link. |
| POST `/api/ps1/optimisation-jobs/{job_id}/cancel` | Request cancellation at a safe solver/persistence boundary. |

All reads require existing same-operator authentication. Missing/other-operator resources
are 404. Wrong write role is 403; invalid JSON/options/baseline selection is 422. Key input
collision is 409. Bounds remain limit 1–200, offset 0–100000, week 1–520. History ordering
is total and deterministic, but offset paging is not a frozen snapshot across concurrent
new inserts. Typed client preserves `optimisePs1ScenarioA`; adds `ps1Optimisations`,
`ps1Optimisation`, `ps1OptimisationAccesses`, `ps1OptimisationOccupancies`,
`ps1OptimisationArtifacts`. Generated OpenAPI and TypeScript are updated.

Example POST (all old options remain accepted):

```json
{"time_limit_seconds":20,"random_seed":0,"physical_nights_per_week":7,
 "baseline_run_id":null,"idempotency_key":"scenario-a-attempt-001"}
```

The bounded job executor is in-process and intended for one API replica. A durable external
queue is still needed for horizontal scaling and restart recovery. Approval/publication and
optional AI integration remain separate. See [manual test guide](PS1_PERSISTENCE_TEST_GUIDE.md) and
[current verification](VALIDATION.md). Real PostgreSQL execution is explicitly distinguished
from SQL parsing and mocked transaction-boundary tests.
