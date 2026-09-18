# Current validation evidence

The release-wide executed checks, exact totals, organiser A/B/C matrix, skipped
PostgreSQL evidence, provisional assumptions and deployment limits are maintained in
[RELEASE_VERIFICATION.md](../../RELEASE_VERIFICATION.md).

Current headline: 441 Python tests passed and 93 PostgreSQL-dependent tests skipped on a
host without PostgreSQL/PostGIS or Docker; strict TypeScript, 35 client tests, 17 browser
workflow checks and the production frontend build passed. SQL assets parse and the Alembic
graph resolves through migration 0009, but those facts are not represented as a live
database migration test.
