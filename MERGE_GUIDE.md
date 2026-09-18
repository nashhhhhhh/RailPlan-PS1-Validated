# Merge guide

PS1 follow-up: migration **0005** adds immutable weekly dataset imports and
`app/ps1-workspace.tsx` adds the dataset UI. Read `PS1_INTEGRATION.md` for the
official task/data mapping and current verification results. PS1 datasets are
separate from the original hourly Singapore demonstration.

## Source selection

| Archive | Merge decision |
|---|---|
| `Nebula-main (1)(1).zip` | Used as the complete frontend/project shell |
| `RailPlan_PostgreSQL_Backend (2).zip` | Used as the authoritative backend because it contains the API-support and conflict-scoring additions |
| `RailPlan_PostgreSQL_Backend (1).zip` | Not overlaid; it is the older subset of backend (2) |
| `backend-conflict-engine(1).zip` | Ported as a feature into backend (2), rather than replacing backend files |

Copying all four archives over one another would lose the newer router-based `app/main.py`, create two different Alembic revisions named `0002`, and disconnect the frontend from the actual API response shapes.

## Resulting migration order

| Revision | Purpose |
|---|---|
| `0001` | Initial PostgreSQL/PostGIS schema |
| `0002` | API indexes and draft-scenario invalidation |
| `0003` | Conflict severity scoring |
| `0004` | Immutable completed analyses and snapshot-backed conflict history |

The conflict package's SQL files were shifted after scoring:

- `006_analysis_history.sql`
- `007_demo_engine_rules.sql`

## Code integration

The conflict engine files live inside the authoritative backend:

- `app/analysis_snapshot.py`
- `app/conflict_engine.py`
- `app/demo_rules.py`

`app/routers/operations.py` now creates and runs an analysis through `POST /api/analyses`. The same router exposes saved summaries and findings. Existing operator scoping and planner-role checks are retained.

The frontend analysis dialog in `app/backend-analysis.tsx` uses `app/analysis-api.ts`. It understands the newer backend's paginated engineering-window response and structured error format.

## Future manual merges

When upstream changes arrive:

1. Merge frontend changes into the project root.
2. Merge backend changes into `railplan-backend` without replacing its whole `app` directory.
3. Add every database change as the next Alembic revision; never reuse an existing revision number.
4. Update both the Alembic file and its `down_revision`.
5. Keep API response contracts synchronized with `app/analysis-api.ts`.
6. Run backend tests, PostgreSQL integration tests, TypeScript checking, and the frontend build.

## Follow-up integration corrections

- Preserved the original coordination-view column order after scoring adds a conflict version column.
- Exported all 50 API paths and 54 schema contracts from this checkout, avoiding older installed packages.
- Kept failed-analysis responses compatible with the frontend error handling.
- Used captured rule severity and blocking when scoring historical automatic findings.
- Added a PostgreSQL integration test and `python -m scripts.verify_features` for the full detection-to-score workflow.

Validation: 181 Python checks passed; 36 database integration checks were skipped
because PostgreSQL/PostGIS is unavailable in the build environment. Live database,
frontend build and browser checks remain outstanding.
