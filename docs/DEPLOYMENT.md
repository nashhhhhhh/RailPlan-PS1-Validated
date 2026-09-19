# Deployment

`python app.py` starts the frontend and stateless FastAPI service together. `python app.py --persisted` also starts PostgreSQL/PostGIS and applies Alembic through revision `0011`. The separate frontend and backend development commands remain available.

PostgreSQL is optional for `/api/ps1/optimise/scenario-b/preview` and `/api/ps1/optimise/scenario-c/preview`, and required for saved instances, history, baselines, and idempotency. Use `/health/ready` to verify database revision and A/B/C solver availability separately from database readiness. Do not expose demo identity authentication in production. Retain bounded request sizes, solver limits, one worker, and the rich-validation publication gate.
