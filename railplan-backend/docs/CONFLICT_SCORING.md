# Conflict severity scoring — v0.3

This release scores existing conflicts deterministically. It does not detect all
conflicts, optimise a schedule, establish rail safety, or grant approval. Existing
rules and legacy scores remain unchanged. New scores appear under `latest_score`
on the coordination queue and conflict detail API, with immutable full history.

## Setup

Use the existing PostgreSQL/PostGIS setup in README, then run:

```bash
alembic upgrade head
python -m app.seed
python -m app.seed_scoring
uvicorn app.main:app --reload
```

The scoring seed works with an already-seeded database. It creates an explicitly
named demo administrator and a synthetic policy, printing their IDs. It does not
change existing users' roles or activate a policy. Development demo authentication
still requires `RAILPLAN_ENV=development`, `RAILPLAN_DEMO_AUTH=1`, and the
`X-Demo-User-Id` header. Production verified authentication is still not integrated.
Fresh and existing installations require migration **0003** before readiness succeeds.

## Calculation

| Component | Default weight | Evidence and prototype normalisation |
|---|---:|---|
| Safety | 35% | Highest of rule/recorded severity: information 10, low 30, medium 60, high 80, critical 100 |
| Operational | 25% | Maximum pairwise scheduled overlap: zero=0; up to 15/30/60/120 minutes=20/40/65/85; longer=100 |
| Resource | 20% | Actual engineer or physical asset assigned to overlapping participant requests=80; otherwise unknown |
| Urgency | 10% | Maximum participant priority: normal 30, high 65, urgent 90 |
| Passenger | 10% | Unknown until a verified passenger/service impact dataset is integrated |

Engineering overlap is not passenger delay. Two requirements of the same equipment
type are not proof that one physical asset is double-booked. Resource scores do
not assess skills, scarcity or overall capacity. Scenario conflicts use scenario
assignment times and resource links, not original request times. Stale assignment
request versions cause HTTP 409.

`risk_score = sum(known component score × policy weight)`. Missing weights stay
in the denominator; no renormalisation or zero-value substitution occurs. The
published score is explicitly a **partial lower bound**, and `risk_upper_bound`
adds 100 times the unknown weight. If no positive-weight evidence is known, the
score and band are null, status is unknown and confidence is zero.

Decimal arithmetic precedes final two-decimal, half-up rounding. Bands apply to
the published score: [0,20) information; [20,40) low; [40,60) medium; [60,80) high;
[80,100] critical. `effective_severity` never drops below either the current rule
or recorded conflict severity. `blocking` comes directly from the rule and does
not depend on the numerical score.

Confidence is a data-quality indicator: known-weight coverage × 0.25 for
synthetic evidence, otherwise × 0.50 because verified provenance/observation age
is absent. Confidence never scales the risk value. All currently supported
calculations are partial or unknown, all policies are unvalidated and automatic
prioritisation is disabled. Complete/not-applicable component types are reserved
for future verified evidence integration; this release does not manufacture them.

## Policies and history

Administrators may create and activate policies. Safety reviewers and
administrators may calculate scores. Authenticated operator users may read them.
Policy weights are configurable, finite, nonnegative, at most six decimal places,
and must total exactly one. The factor normalisers are versioned in Python under
`railplan-scoring/1.0.0`; this release does not execute configurable expressions.

Each policy version is immutable from creation. Activation is operator-wide and
immediate; activation periods cannot overlap and closed intervals cannot change.
Explicit scoring against an inactive version is allowed for comparisons, with
`active_policy_matches=false`. Activation never marks a prototype policy validated.

Migration 0003 adds four tables: `scoring_source_revision`,
`scoring_policy_activations`, `conflict_scores`, `score_idempotency_keys`; extends
`scoring_policies` with operator/definition fields; and adds conflict versions.
Legacy global policy rows are retained but excluded from the scoring API.
Component breakdowns and evidence are stored inside immutable result/input JSONB
snapshots, not overwritten in the legacy `conflict_score_components` table.
Policy/input fingerprints and engine version uniquely identify each calculation.
Score, idempotency mapping, audit and activity writes share one transaction.

## API workflow

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/scoring-policies` | List/create immutable policies |
| GET | `/api/scoring-policies/{id}` | Read policy |
| POST | `/api/scoring-policies/{id}/activate` | Activate for operator |
| GET | `/api/conflicts/{id}/scoring-context` | Read version/fingerprint and role eligibility |
| POST | `/api/conflicts/{id}/scores` | Calculate or replay |
| GET | `/api/conflicts/{id}/scores` | Paginated history |
| GET | `/api/conflicts/{id}/scores/latest` | Latest calculation, or null |
| GET | `/api/conflict-scores/{id}` | Full stored evidence and live freshness |

Read scoring-context immediately before POSTing:

```json
{
  "policy_id": "<policy UUID>",
  "expected_conflict_version": 1,
  "expected_input_fingerprint": "<64-character hash from scoring-context>",
  "idempotency_key": "<unique operation key, at least 8 characters>"
}
```

Same key/body replays the stored result, including its current stale status, even
if data subsequently changed. Reusing the key for different inputs returns 409.
A different key with identical evidence/policy reuses the calculation. New
calculations require matching conflict version and input fingerprint; otherwise
reload context and ask the user to retry. No automatic client retry hides 409s.

## Freshness and concurrency

A conservative database-wide revision changes on relevant source mutations,
including resource availability and policy activation. A share lock stabilises
snapshot capture; existing operator advisory locks serialize API mutations.
Revision or engine changes mark old scores stale without modifying history.
Unrelated operator edits can also mark a score stale: deliberate conservative
invalidation for this prototype, with potential contention at higher throughput.
Use scoped revisions and scheduled background scoring before a large deployment.

`fresh` means score inputs have not changed since capture. It does **not** mean
the existing analysis detected all current conflicts: legacy analysis freshness
is unknown, and `can_certify_current_schedule` is always false. No live detector
or operational approval path has been added.

## UI integration

`frontend/scoring.ts` exports `ScoringClient` and `scorePanel`. The adapter supplies
five factor bars, explicit Unknown labels, contributions, missing-input explanations,
confidence, blocking, policy/engine identity, timestamp, stale status and role-based
recalculate eligibility. Call `context`, then `calculate`; use `latest` and
`history` for panels. These are client/adapters for the existing UI; the hosted
website has not been modified or deployed by this backend update.

## Verification

```bash
python -m pytest -q
cd frontend
npm install
npm test
```

Database tests require an empty disposable PostgreSQL 16+/PostGIS database named
`railplan_test*` through `TEST_DATABASE_URL`. They install migrations in an outer
transaction and roll back. Tests cover persistence, deduplication, key collisions,
staleness, immutable history, activation and failure rollback, but were not run
in this environment. Real multi-connection concurrency/load testing is also
outstanding. Python unit/API/static checks and TypeScript/Node tests run without
a database. Regenerate OpenAPI/client schema types with
`python -m scripts.export_contracts`.
