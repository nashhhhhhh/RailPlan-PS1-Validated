# API endpoint inventory

## Scenario B optimisation

- `POST /api/ps1/optimise/scenario-b/preview` — stateless, unauthenticated, no PostgreSQL/history; accepts `instance_files` and bounded solver options.
- `POST /api/ps1/instances/{instance_id}/optimise/scenario-b` — planner/admin, immutable PostgreSQL terminal history.
- `GET /api/ps1/instances/{instance_id}/optimisations?scenario=B` — scenario-filtered history.

Responses distinguish solver status, primary optimality, lexicographic completion, physical validation, publication state, judge validation, and internal-only score verification.

## PS1 Scenario A optimisation

`POST /api/ps1/instances/{instance_id}/optimise/scenario-a` computes a bounded CP-SAT
candidate for a same-operator planner/administrator. It is separate from the unavailable
legacy nightly worker. It now saves an immutable terminal run; no publication write.
Added GET history, detail, accesses, occupancies and accepted-artifact routes are documented
in [PS1_OPTIMISATION_PERSISTENCE.md](PS1_OPTIMISATION_PERSISTENCE.md).
Solver contracts/limits: [PS1_OPTIMISATION.md](PS1_OPTIMISATION.md).

## PS1 validator additions

`POST /api/ps1/validate` is stateless and unauthenticated. The following persisted routes
are operator-scoped: `POST/GET /api/ps1/instances/{id}/validations`,
`GET /api/ps1/validations/{id}`, and `GET /api/ps1/validations/{id}/violations`.
Creating a persisted run requires planner or administrator. Detailed input/report models,
pagination, limits, idempotency and error semantics: [PS1_VALIDATION.md](PS1_VALIDATION.md).
All prior routes remain available; OpenAPI is regenerated from the complete application.

Version 0.3. Existing endpoints below are retained. The additional scoring endpoints,
role requirements, concurrency tokens and replay semantics are documented in
[CONFLICT_SCORING.md](CONFLICT_SCORING.md); `openapi.json` includes all routes.

## UI inspection and changes

Inspected the existing page.tsx, rail-data.ts and singapore-map.tsx. Existing state-only actions
included request composition, drag/resize, locks, presets, approval Boolean and notifications.
Reused SQL tables, request creation, snapshot helpers and read views. Added routers and an additive
migration; no original schema tables were rebuilt and no frontend visual components were changed.

## Status

| Area | Status | Evidence/remaining check |
|---|---|---|
| Typed contracts, errors, filter bounds, preview rules | Implemented and tested | Python unit and API contract checks |
| TypeScript client/adapters | Implemented and tested | Compiler and 12 client tests |
| CRUD, scenario persistence, locks, activity, scoped reads | Implemented; database integration testing pending | 28 PostgreSQL/PostGIS tests provided |
| Production OIDC | Contract/boundary only | Production fails closed |
| Analysis/optimisation workers | Intentionally unavailable | POST returns 503; no queue insert |
| Copilot | Contract only | Capability false; no fake responses |
| Operational approval/publication | Intentionally unavailable | Write routes return 501 |
| Hosted UI wiring | Adapter delivery only | Copy data-layer client and connect existing handlers |

## Routes

| Method | Route | Group |
|---|---|---|
| GET | `/api/activity` | Command centre and coordination |
| POST | `/api/activity/read` | Command centre and coordination |
| POST | `/api/analyses` | Command centre and coordination |
| GET | `/api/analyses/{analysis_id}` | Command centre and coordination |
| GET | `/api/approvals/{approval_id}` | Command centre and coordination |
| POST | `/api/approvals/{approval_id}/decisions` | Command centre and coordination |
| GET | `/api/capabilities` | Command centre and coordination |
| GET | `/api/command-centre/{window_id}` | Command centre and coordination |
| GET | `/api/conflicts` | Command centre and coordination |
| GET | `/api/conflicts/{conflict_id}` | Command centre and coordination |
| GET | `/api/engineering-windows` | Command centre and coordination |
| GET | `/api/engineering-windows/{window_id}` | Command centre and coordination |
| GET | `/api/engineers` | Network and resources |
| GET | `/api/equipment` | Network and resources |
| POST | `/api/locks/{lock_id}/release` | Requests and locks |
| GET | `/api/maintenance-requests` | Requests and locks |
| POST | `/api/maintenance-requests` | Requests and locks |
| GET | `/api/maintenance-requests/{request_id}` | Requests and locks |
| PATCH | `/api/maintenance-requests/{request_id}` | Requests and locks |
| POST | `/api/maintenance-requests/{request_id}/cancel` | Requests and locks |
| GET | `/api/maintenance-requests/{request_id}/locks` | Requests and locks |
| POST | `/api/maintenance-requests/{request_id}/locks` | Requests and locks |
| POST | `/api/maintenance-requests/{request_id}/submit` | Requests and locks |
| GET | `/api/network/lines` | Network and resources |
| GET | `/api/network/sectors` | Network and resources |
| GET | `/api/network/stations` | Network and resources |
| POST | `/api/optimisation-runs` | Command centre and coordination |
| GET | `/api/optimisation-runs/{run_id}` | Command centre and coordination |
| GET | `/api/reference-data` | Command centre and coordination |
| GET | `/api/resources/availability` | Network and resources |
| GET | `/api/scenarios` | Scenarios |
| POST | `/api/scenarios` | Scenarios |
| GET | `/api/scenarios/compare` | Scenarios |
| GET | `/api/scenarios/{scenario_id}` | Scenarios |
| GET | `/api/scenarios/{scenario_id}/approval` | Command centre and coordination |
| POST | `/api/scenarios/{scenario_id}/approval` | Command centre and coordination |
| PATCH | `/api/scenarios/{scenario_id}/assignments/{assignment_id}` | Scenarios |
| POST | `/api/scenarios/{scenario_id}/assignments/{assignment_id}/preview` | Scenarios |
| GET | `/api/scenarios/{scenario_id}/changes` | Scenarios |
| POST | `/api/scenarios/{scenario_id}/clone` | Scenarios |
| GET | `/api/teams` | Network and resources |
| GET | `/api/timeline/{window_id}` | Command centre and coordination |
| GET | `/api/workzones` | Network and resources |
| GET | `/api/workzones/{workzone_id}` | Network and resources |
| GET | `/health` | Health |
| GET | `/health/live` | Health |
| GET | `/health/ready` | Health |

42 unique paths; 47 operations.

## Compatibility and semantics

- Original /api routes are retained. POST /analyses and /optimisation-runs now reject unavailable
  work instead of leaving jobs queued forever.
- Create-request defaults to submitted for compatibility; submit:false enables the new draft flow.
- Original scenario detail summary/changes remain, with assignments and capabilities added.
- Timeline preserves its array response and adds bounded limit/offset parameters.
- Error responses now use {error:{code,message,fields,correlation_id,guidance}}.
- 201 means created; 409 means stale or incompatible state; 422 means invalid input.
- No background POST returns 202 because no durable worker is connected.
- GET conflict collections require analysis_id; stale/unknown snapshots are not treated as current.
- API writes serialize by operator advisory lock. This does not protect future workers that bypass
  the shared service policy; those integrations must adopt the same locking/validation rules.

## Future integration contracts

app/worker_contracts.py separates execution_status from solver_outcome so a timeout can still
return a feasible incumbent. The existing run table's legacy status is not reinterpreted as a
verified solver outcome. Before enabling workers, add durable dispatch, versioned complete inputs,
cancellation/retry state and independent domain validation.

Future copilot tools should expose request retrieval, conflict evidence, scenario comparison,
resource candidates and draft proposals through the same services. No direct SQL or approval bypass.
