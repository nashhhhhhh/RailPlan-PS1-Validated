# PS1 integration

The organiser source pack is preserved under `railplan-backend/data/PS1`: eight input
CSVs, topology references, challenge documentation and three sample submission CSVs. The
sample submission is reference material for validation and dashboard exploration; it is
not described as a RailPlan-generated schedule.

The dashboard imports the eight input CSVs, shows their lineage, renders the Line Alpha
and Line Beta topology, and explains Scenario A/B/C validation policies. FastAPI provides
stateless parse/validation APIs and a database-free Scenario A optimisation preview. Saved
instances, validation history, sealed optimiser runs and asynchronous Scenario A jobs use
the migration chain through 0009.

The validator supports A, B and C. The supplied authoritative source tree contains the
Scenario A optimiser; no Scenario B/C optimiser modules or nested release archives were
present. This release preserves that boundary instead of constructing replacement solvers.

## Data semantics

- `physical_night`: network-wide slot 1..7 within a week, used for concurrency and closure.
- `access_night`: local contract/activity-type/week allocation index.
- `co_share_group`: possession label scoped to one location/week.

Equal local indices or group labels do not establish global concurrency. The source data
does not provide a dated engineering-night calendar, so the slot-to-date mapping remains a
provisional policy. Internal validation does not claim judge or operational approval.

## Main endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/ps1/example` | Bundled source instance and parsed preview |
| `POST /api/ps1/preview` | Stateless structural validation of eight CSVs |
| `POST /api/ps1/validate` | Stateless A/B/C submission validation |
| `POST /api/ps1/optimise/scenario-a/preview` | Stateless Scenario A solve with rich validation |
| `POST /api/ps1/instances` | Authenticated immutable import |
| `POST /api/ps1/instances/{id}/optimise/scenario-a` | Synchronous sealed Scenario A run |
| `POST /api/ps1/instances/{id}/optimise/scenario-a/jobs` | Durable asynchronous job |

Use `python app.py` for database-free local work or `python app.py --persisted --seed`
with Docker for saved features. See [README.md](README.md),
[PS1 validation](railplan-backend/docs/PS1_VALIDATION.md),
[PS1 optimisation](railplan-backend/docs/PS1_OPTIMISATION.md), and the
[release verification report](RELEASE_VERIFICATION.md).

Ollama/Qwen is optional and is not involved in parsing, constraints, feasibility,
validation, scoring or the publication gate.
