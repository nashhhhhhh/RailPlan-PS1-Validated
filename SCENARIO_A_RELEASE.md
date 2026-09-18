# Scenario A release history

Scenario A retains the original bounded, deterministic OR-Tools CP-SAT implementation,
explicit physical-night assignments, staged objectives, CSV exporter and fail-closed rich
validation gate. This integration release does not redesign its documented rules.

Later releases added sealed persistence in migration 0007, stateless preview, durable job
control in migrations 0008–0009, the dashboard workflow, generated clients, deployment
support and current verification evidence. Read
[PS1_OPTIMISATION.md](railplan-backend/docs/PS1_OPTIMISATION.md),
[PS1_OPTIMISATION_PERSISTENCE.md](railplan-backend/docs/PS1_OPTIMISATION_PERSISTENCE.md)
and [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md) for the current contract.

The organiser source/sample files remain unchanged reference inputs. Official judge
validation and score verification have not run.
