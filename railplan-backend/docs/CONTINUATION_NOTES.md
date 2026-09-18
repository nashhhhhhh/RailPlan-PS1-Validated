# Continuation notes

- Migration head is 0009. Migration 0007 seals terminal Scenario A evidence; 0008–0009
  add durable, audited optimisation-job status/progress/cancellation.
- The Scenario A solver rules remain unchanged. Stateless preview and persisted execution
  both use explicit physical nights and the same rich-validation publication gate.
- The internal validator supports Scenarios A, B and C. This checkout contains no Scenario
  B/C optimiser source, so do not substitute the organiser samples or fabricate output.
- Before deployment, run the 93 retained PostgreSQL tests with three distinct disposable
  `railplan_test*` databases. The 2026-09-19 host lacked PostgreSQL/PostGIS and Docker.
- The in-process job executor requires one API replica. External durable queue and restart
  recovery are future deployment work.
- Keep `physical_night`, contract-local `access_night` and location-local
  `co_share_group` separate. No dated engineering-night calendar was supplied.
- Ollama/Qwen remains optional and outside feasibility, validation and scoring.
- Current evidence and limitations: `../../RELEASE_VERIFICATION.md`.
