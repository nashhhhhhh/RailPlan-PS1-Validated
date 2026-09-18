# PS1 persistence: setup and manual verification

Use PostgreSQL 16+ with PostGIS. Nothing in this guide deploys the app. Keep existing
data backed up; immutable-history downgrade deliberately refuses destructive removal.
All test databases below must be explicitly created, empty and disposable. The committed
and migration suites leave their schemas/data for inspection and require fresh databases
on the next run. They never drop an existing schema or substitute SQLite.

## Install and automated checks

From `railplan-backend`, using your project's Python virtual environment:

```bash
python -m pip install -e ".[test]"
python -m pytest tests/test_ps1_optimisation.py tests/test_ps1_optimisation_persistence.py -q
python -m pytest -q
python -m scripts.export_contracts
```

From the project root: `corepack pnpm exec tsc --noEmit` and `corepack pnpm build`.
From `railplan-backend/frontend`: `npm test`.

### Database test configuration — Bash

Replace connection placeholders locally; do not check credentials into source:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_rollback'
export TEST_COMMITTED_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_committed'
export TEST_MIGRATION_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_migration'
python -m pytest tests/test_postgres.py tests/test_ps1_optimisation_postgres.py -q -rs
```

### Database test configuration — PowerShell

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_rollback'
$env:TEST_COMMITTED_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_committed'
$env:TEST_MIGRATION_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_migration'
python -m pytest tests/test_postgres.py tests/test_ps1_optimisation_postgres.py -q -rs
```

The three database names must differ and start with `railplan_test`. The old rollback
suite creates its schema inside a transaction and rolls it back. The committed suite
uses real committed schema/data and separate connections for sealing, race and reload
tests. The migration test uses its own fresh database, explicitly passes its URL as
`DATABASE_URL` to Alembic subprocesses, upgrades through 0009, attempts the
expected-refused downgrade to 0008 and verifies head remains 0009. Missing URLs cause
explicit skips.

**Setting TEST_DATABASE_URL alone does not redirect Alembic.** Never run Alembic against
an unintentionally inherited development/production DATABASE_URL. For a separate manual
migration verification, use another new disposable database rather than the rollback fixture.
Exact shell commands (only after confirming the variable points to that disposable DB):

```bash
# Inline assignment affects only the child command; it does not overwrite your shell's URL.
DATABASE_URL="$TEST_MIGRATION_DATABASE_URL" python -m alembic upgrade head
DATABASE_URL="$TEST_MIGRATION_DATABASE_URL" python -m alembic current
DATABASE_URL="$TEST_MIGRATION_DATABASE_URL" python -m alembic downgrade 0008
# Expected: nonzero exit requiring job audit history to be archived first.
DATABASE_URL="$TEST_MIGRATION_DATABASE_URL" python -m alembic current
# Expected: still 0009. Do not disable triggers or force history deletion.
```

```powershell
$previousDatabaseUrl = $env:DATABASE_URL
try {
    $env:DATABASE_URL = $env:TEST_MIGRATION_DATABASE_URL
    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Upgrade failed' }
    python -m alembic current
    python -m alembic downgrade 0008
    if ($LASTEXITCODE -eq 0) { throw 'Unexpected destructive downgrade success' }
    python -m alembic current  # Must still show 0009.
} finally {
    $env:DATABASE_URL = $previousDatabaseUrl
}
```

If you use the manual migration commands, do not subsequently point the empty-database
migration test at that already-initialised database. Create a fresh one instead.

## Manual application test — PowerShell

Use a separate local application/smoke database. Explicitly set its DATABASE_URL, apply
`python -m alembic upgrade head`, then `python -m app.seed`. The pinned solver dependency
is unchanged. In the server terminal enable only the existing local-development demo auth:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@localhost:5432/railplan_test_smoke'
$env:RAILPLAN_ENV = 'development'
$env:RAILPLAN_DEMO_AUTH = '1'
python -m alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, within `railplan-backend` and using the same virtual environment:

```powershell
$api = 'http://127.0.0.1:8000'
$planner = python -c "from app.seed import uid; print(uid('planner'))"
$headers = @{ 'X-Demo-User-Id' = $planner.Trim() }
$fixtureJson = python -c "import json; from scripts.create_ps1_smoke_fixture import files; print(json.dumps({'name':'Persistence smoke fixture','files':files()}))"
$instance = Invoke-RestMethod -Uri "$api/api/ps1/instances" -Method Post -Headers $headers -ContentType 'application/json' -Body $fixtureJson
$iid = $instance.id
$options = @{
    time_limit_seconds = 5
    idempotency_key = 'manual-smoke-001'
    locked_placements = @(@{ activity_id='SMOKE-A1'; access_seq=1; week=2; physical_night=6; access_night=1 })
}
$body = $options | ConvertTo-Json -Depth 10
$saved = Invoke-RestMethod -Uri "$api/api/ps1/instances/$iid/optimise/scenario-a" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$rid = $saved.run_id
$saved | ConvertTo-Json -Depth 100
```

This is a generated **synthetic one-activity test instance**, not a modification of the
organiser dataset. With ordinary local resources it is known feasible and small enough
for a success-path test. Require `publishable=true`, `physical_validation_complete=true`,
empty hard violations, `created=true` and a run ID. Physical night must be 6 while local
access index is 1. The weighted overrun should be internal **9.10** (7 days × 1.3).
Do not require the large public dataset to reach OPTIMAL or find a short-budget incumbent.
If even the small fixture is bounded under extreme load, retry with a new key and longer
budget; never count UNKNOWN as a successful schedule.

### Reload, restart, history and downloads

```powershell
$detail = Invoke-RestMethod -Uri "$api/api/ps1/optimisations/$rid" -Headers $headers
$history = Invoke-RestMethod -Uri "$api/api/ps1/instances/$iid/optimisations?limit=10&offset=0" -Headers $headers
$accesses = Invoke-RestMethod -Uri "$api/api/ps1/optimisations/$rid/accesses?week=2" -Headers $headers
$occupancies = Invoke-RestMethod -Uri "$api/api/ps1/optimisations/$rid/occupancies?week=2" -Headers $headers
$artifacts = Invoke-RestMethod -Uri "$api/api/ps1/optimisations/$rid/artifacts" -Headers $headers
New-Item -ItemType Directory -Path './saved-smoke' -ErrorAction Stop
$encoding = [System.Text.UTF8Encoding]::new($false)
foreach ($file in $artifacts.files.PSObject.Properties) {
    [System.IO.File]::WriteAllText((Join-Path "$pwd/saved-smoke" $file.Name), [string]$file.Value, $encoding)
}
[System.IO.File]::WriteAllText("$pwd/saved-smoke/report.json", ($detail | ConvertTo-Json -Depth 100), $encoding)
```

Stop and restart the API process using the **same application database**. Repeat the
GETs. IDs, complete result/validation snapshots, assignments and exact CSV strings must
match. Preserve report JSON with CSVs because the organiser schemas omit physical nights.
The run stays immutable. `judge_validation` remains `not_run` and `score_verification`
remains `internal_only`; this does not grant approval or official acceptance.

### Key reuse, collision, new attempt and baseline

Repeat the original POST using the unchanged `$body`: same run ID, `created=false`,
`reused=true`; no solve. Change `random_seed` while keeping `manual-smoke-001`: HTTP 409.
Change the key to `manual-smoke-002`: a new attempt/ID is allowed even with otherwise
identical settings. A baseline POST can contain `baseline_run_id=$rid`, empty or omitted
`baseline_placements`, and a fresh key. Saved access rows must show baseline week/night.
Baseline is soft; locks remain hard. A run from a different instance/operator is 404;
a visible rejected run is 422 as a baseline; explicit placements plus a baseline ID is 422.

### Diagnostic failure run

Make a second valid instance whose activity starts in week 3, then lock its only access
to week 1. This is an accepted request with contradictory scheduling constraints, not a
malformed JSON/reference request:

```powershell
$lateFixture = $fixtureJson | ConvertFrom-Json
$lateFixture.files.'08_ACTIVITY_DETAILS.csv' = $lateFixture.files.'08_ACTIVITY_DETAILS.csv'.Replace('2027-01-04','2027-01-18')
$late = Invoke-RestMethod -Uri "$api/api/ps1/instances" -Method Post -Headers $headers -ContentType 'application/json' -Body ($lateFixture | ConvertTo-Json -Depth 20)
$failedBody = @{ time_limit_seconds=5; idempotency_key='manual-infeasible-001'; locked_placements=@(@{activity_id='SMOKE-A1';access_seq=1;week=1;physical_night=1}) } | ConvertTo-Json -Depth 10
$failed = Invoke-RestMethod -Uri "$api/api/ps1/instances/$($late.id)/optimise/scenario-a" -Method Post -Headers $headers -ContentType 'application/json' -Body $failedBody
```

Expect INFEASIBLE, `publishable=false`, a saved run ID, no accepted CSVs/access/occupancy
rows and structured diagnostics. Detail/history work; artifacts returns HTTP 409.
Repeating the key reuses that failed run. Invalid references instead return 422 and create
no run. Wrong-operator GET/POST returns 404; a viewer cannot submit optimisation.

## Bash API equivalent

Use the same local server configuration with `export` rather than `$env:`. To import and
create the small fixture with curl (jq is used only to extract IDs):

```bash
api='http://127.0.0.1:8000'
planner=$(python -c "from app.seed import uid; print(uid('planner'))")
python -c "import json; from scripts.create_ps1_smoke_fixture import files; print(json.dumps({'name':'Persistence smoke fixture','files':files()}))" > /tmp/ps1-smoke-input.json
curl --fail-with-body -sS -H "X-Demo-User-Id: $planner" -H 'Content-Type: application/json' --data-binary @/tmp/ps1-smoke-input.json "$api/api/ps1/instances" > /tmp/ps1-smoke-instance.json
iid=$(jq -r .id /tmp/ps1-smoke-instance.json)
curl --fail-with-body -sS -H "X-Demo-User-Id: $planner" -H 'Content-Type: application/json' --data '{"time_limit_seconds":5,"idempotency_key":"bash-smoke-001"}' "$api/api/ps1/instances/$iid/optimise/scenario-a" > /tmp/ps1-smoke-run.json
rid=$(jq -r .run_id /tmp/ps1-smoke-run.json)
curl --fail-with-body -sS -H "X-Demo-User-Id: $planner" "$api/api/ps1/optimisations/$rid"
curl --fail-with-body -sS -H "X-Demo-User-Id: $planner" "$api/api/ps1/optimisations/$rid/artifacts"
```

The unlocked Bash example normally finishes in week 1 with zero overrun. Apply the same
restart/history/reuse/collision/failed-instance checks described above. Test outcomes in
[VALIDATION.md](VALIDATION.md) distinguish executed checks from unavailable PostgreSQL tests.
