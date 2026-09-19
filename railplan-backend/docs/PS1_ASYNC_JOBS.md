# PS1 asynchronous optimisation jobs

RailPlan provides the same persisted job lifecycle for Scenarios A, B, and C:

`QUEUED` → `RUNNING` → `SUCCEEDED`, `FAILED`, or `CANCELLED`.

`SUCCEEDED` means the bounded optimiser invocation completed and its terminal evidence was stored. It does not mean that a publishable schedule exists. Inspect `solver_status`, `validation_result`, and `artifact_eligible` after polling the job.

## API

- `POST /api/ps1/instances/{instance_id}/optimise/scenario-a/jobs`
- `POST /api/ps1/instances/{instance_id}/optimise/scenario-b/jobs`
- `POST /api/ps1/instances/{instance_id}/optimise/scenario-c/jobs`
- `GET /api/ps1/optimisation-jobs/{job_id}`
- `GET /api/ps1/instances/{instance_id}/optimisation-jobs`
- `POST /api/ps1/optimisation-jobs/{job_id}/cancel`

The list route accepts `limit`, `offset`, and an optional `scenario=A|B|C`. Results are ordered by creation time descending, then job ID descending. All operations are scoped to the authenticated operator; an inaccessible job is reported as not found.

The start response is HTTP 202. Poll the retrieve route until a terminal state is returned. A terminal job is immutable, and attempting to cancel it returns HTTP 409.

## Durable evidence and idempotency

PostgreSQL stores job identity, operator and creator ownership, scenario, input fingerprint, the bounded solver controls, the fully resolved option snapshot, validator and policy versions, timestamps, progress, diagnostics, and the linked immutable terminal optimisation run. The linked run contains solver status, objective components, best objective and bound, validation output, and artifact eligibility.

An idempotency key is scoped by operator, instance, and scenario. Repeating the same key and effective options returns the existing job. Reusing it with different effective input returns HTTP 409. The same caller key may be used independently for A, B, and C.

## Cancellation, restart, and execution limits

Cancellation is cooperative. A queued job is sealed as cancelled immediately. A running CP-SAT call observes cancellation at the next job-layer solver boundary; its configured wall-clock and deterministic limits remain the hard bound. A cancelled candidate is never persisted as a run and no partial CSV is published.

The executor is deliberately process-local and bounded by `RAILPLAN_OPTIMISER_WORKERS` (default 1, maximum 4). PostgreSQL state is durable, but execution itself is not restartable. In the supported single-API-process configuration, polling or starting work after a restart marks jobs missing from the local executor registry as `FAILED` with `abandoned_after_process_restart` diagnostics. Multi-replica execution requires an external durable queue and worker ownership protocol; the current adapter must not be used as if it provided that guarantee.

## Publication gate

Artifacts are exposed only through the existing run artifact endpoint when the optimiser returned a feasible candidate and rich validation confirms all of the following:

- `feasible` is true;
- `physical_validation_complete` is true;
- `hard_violations` is empty.

`UNKNOWN` remains distinct from `INFEASIBLE`. An unknown result without an accepted incumbent, an infeasible or model-invalid result, a validator-rejected candidate, a failed job, and a cancelled job never expose CSV files. The internal result name `VALIDATION_FAILED` represents validator rejection. Feasibility is determined only by the deterministic optimiser and rich validator; optional AI integrations have no role in it.
