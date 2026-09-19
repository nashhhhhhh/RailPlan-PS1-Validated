# PS1 dataset integration

## Scenario A/B/C integration

The command dashboard still reads bundled official source CSVs and organiser Scenario A reference output. **Open optimiser** opens `PS1Workspace`, where Scenario B and C run as database-free local previews or saved PostgreSQL optimisations. Preview is stateless but still calls FastAPI. A/B/C submission validation remains available, and organiser samples remain labelled as reference output.

Optimiser-run persistence is now included in migration **0007**, with dedicated sealed
PS1 tables and retrieval APIs. It preserves the importer, validator and CSV schemas;
see [persistence documentation](railplan-backend/docs/PS1_OPTIMISATION_PERSISTENCE.md).

## Current submission-validator update

The input integration is preserved. A separate deterministic validator now handles the
three submission CSVs, all 21 hard-rule families, Decimal objectives, API/UI reporting and
immutable history (migration **0006**). See
[PS1_VALIDATION.md](railplan-backend/docs/PS1_VALIDATION.md) for contracts and assumptions.
Version `ps1-validator/1.1.0` is **not** the judge's validator. The sample has
full workload, consistent results, zero hard violations and 70 alignment warnings.
Its internal objective is 48.30. CSV-only feasibility does not establish physical safety.
Scenario A/B/C CP-SAT optimisation is now available; see
[PS1_OPTIMISATION.md](railplan-backend/docs/PS1_OPTIMISATION.md). Generated candidates
must pass rich validation. Official-judge comparison remains outstanding.
The input-only release notes
and verification counts below are historical; current checks are in `docs/VALIDATION.md`.

The organiser's PS1 is a weekly track-access allocation problem on fictional
Line Alpha (ALP) and Line Beta (BET). It is not the existing Singapore MRT
nightly maintenance demo. This integration preserves that distinction.

## What is now included

- Exact supplied PS1 source pack in `railplan-backend/data/PS1`, including its README,
  eight input CSVs, topology references and sample submission files.
- Strict CSV importer with typed numeric/date fields, topology and reference
  checks, duplicate detection, predecessor cycle checks and full workload counts.
- Derived occupied spans containing all tunnel sectors and the book-in,
  intermediate and book-out platforms. All 54 public-instance spans match the
  locations in the organiser's sample occupancy file.
- FastAPI preview and import APIs plus additive migration **0005**. Each saved
  instance retains exact source CSV strings and parsed data in immutable JSONB
  snapshots, scoped by operator. Identical imports reuse the existing instance.
  Changed instances get new IDs; existing nightly requests/scenarios are untouched.
- `PS1 · Hackathon dataset` button in the main UI: public example, eight-file upload,
  contract/activity/supply tables, line topology, activity spans, workload totals,
  A/B/C policy descriptions and saved-instance loading.
- Clearly labelled organiser sample CSV downloads. These are reference files,
  not computed outputs for an uploaded instance.

## Public instance

| Item | Count / value |
|---|---|
| Lines | 2 |
| Station records | 20 (18 unique IDs; hubs occur on both lines) |
| Tunnel sectors | 18 before adding bounds |
| Capacity locations | 76 tunnel/platform/bound combinations |
| Contracts | 14 |
| Activities | 54; retain IDs including gaps |
| Required workload | 192 standard access-night work units |
| Dependencies | 6 predecessor links |
| Planning horizon | 30 weeks, 4 January–1 August 2027 |

`03_SECTORS.csv.seq` is globally numbered: Beta begins at 10, while Beta's
station sequence begins at 1. Span expansion therefore uses station endpoints,
not equality of the two sequence fields. H01/H02 remain separate capacities per
line/bound; neither an interchange ID nor a shared label merges their capacities.

## Run

Follow README for frontend installation and backend PostgreSQL/PostGIS setup.
Upgrade the backend with `alembic upgrade head` and start FastAPI. Existing demo
authentication uses `RAILPLAN_ENV=development`, `RAILPLAN_DEMO_AUTH=1` and the
`X-Demo-User-Id` header. The normal demo seed provides a planner identity.

Open **PS1 · Hackathon dataset**, then **Load organiser dataset**. The bundled
example works without FastAPI. For a hidden instance, select all eight CSVs from
its `01_data` directory using **Import 8 CSV files**. Import preview needs FastAPI
but not a database. **Save dataset** and saved-instance listing need PostgreSQL
and the planner identity. Configure the backend address in the connection panel;
set CORS to the frontend origin when running the two services separately.

| Endpoint | Purpose |
|---|---|
| GET `/api/ps1/example` | Bundled public instance, raw files and parsed preview |
| POST `/api/ps1/preview` | Stateless structural validation |
| POST `/api/ps1/instances` | Authenticated immutable import |
| GET `/api/ps1/instances` | Operator-scoped paginated list |
| GET `/api/ps1/instances/{id}` | Saved dataset |

POST JSON: `{"name":"My instance","files":{"01_LINES.csv":"line_code,line_name\n...",...}}`.
Select CSVs, not the ZIP or the sample output files. Limits: 4 MB combined CSV
text and 20,000 rows per file. The importer implements the published eight-file
schema and fixed ALP/BET topology. Unexpected schema/rule changes are rejected
for review instead of silently guessed. No uploaded code is executed.

Regenerate the bundled preview and OpenAPI after parser changes:

```bash
cd railplan-backend
python -m scripts.export_ps1
python -m scripts.export_contracts
python -m pytest -q
```

## Scheduling work still required

This release integrates the dataset; it does not generate a PS1 solution. The
nightly conflict detector is not the PS1 validator. The following need their own
weekly solver and validation path:

1. Full activity workload delivery, planned start weeks and predecessors.
2. Location/week possession groups, PM-alone / PC+C / C+C legal mixes.
3. Live/Consist buffers, opposite-bound mirroring and Live-only interchange closure.
4. Contract/type weekly night budgets and per-night workfront caps. `access_night`
   is local to contract+type+week, not a shared global calendar night.
5. A/B/C policies, ECLO work yield (1.5), C's two-week ECLO window per line,
   completion dates and official penalty calculation.
6. Generation of all three required CSV outputs separately for A, B and C.
7. Validation with the judges' reference validator and hidden-instance testing.

The supplied ZIP does not contain the referenced `trackaccess` validator/CLI.
It includes only data, documentation, topology references and sample output.
The README also has conflicting explanatory prose about penalty ordering and
buffer/co-sharing interactions. Preserve the explicit numeric formulas (excess
access=7, ECLO=5; contract priority bands=100/10/1 with activity nudges) and confirm
edge-case semantics against the actual reference validator before claiming a
feasible or scored submission. Existing 0–100 conflict severity scores are not
the competition's schedule objective score.

## DataMall and AI

The supplied DataMall guide describes real Singapore transport APIs, including
AccountKey authentication and geospatial downloads. PS1 has fictional station IDs
and no latitude/longitude mapping, so no DataMall call is required for its import
or core scheduling. The guide's Facilities Maintenance endpoint concerns station
lifts, not a supply of track possessions. No account key was provided or required.
DataMall can support the separate Singapore demonstration later; no arbitrary
mapping of Alpha/Beta stations onto real MRT stations is introduced here.

The selected AI stack remains **Ollama + Qwen3**. It can later query these saved
instances and explain solver results. AI integration is still pending and does
not substitute for the PS1 scheduler or reference validator.

## Validation limits

Executed for this update: **204 Python tests passed**, TypeScript checking passed,
and `npm run build` completed successfully. The build reports an existing large
bundle warning. Frontend checking/build reused the available dependency installation;
a clean lockfile installation and browser interaction test remain to be run.
**38 PostgreSQL integration tests were skipped** without `TEST_DATABASE_URL`.

Parser tests include all supplied activities, source/sample span comparison,
changed-instance workload, duplicate/invalid records, missing references, cycles,
and stateless API operation. Database tests for retained CSVs, deduplication,
immutability and operator scoping are provided but require a PostgreSQL test
database. Live database tests were not run in this environment.
