# PS1 persistence release history

Migration 0007 introduced immutable terminal Scenario A runs, exact result/validation
snapshots, explicit access/occupancy/contract rows, accepted CSV artifacts, baselines and
operator/instance-scoped idempotency. Those tables and their sealing rules remain intact.

Migrations 0010–0011 add a separate durable job-control table with audited guarded state,
progress and cancellation. The synchronous endpoint remains supported. Failed solver
outcomes persist as diagnostics and never publish candidate CSVs.

Current transaction behavior, endpoints and limits are documented in
[PS1_OPTIMISATION_PERSISTENCE.md](railplan-backend/docs/PS1_OPTIMISATION_PERSISTENCE.md).
Exact executed and skipped evidence is in [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md).
