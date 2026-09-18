# Deployment

Run the frontend and FastAPI as separate processes. `python app.py` serves/launches the frontend only. Install the backend package (including OR-Tools 9.14), configure CORS, and apply Alembic through revision `0009`.

PostgreSQL is optional for `/api/ps1/optimise/scenario-b/preview` and `/api/ps1/optimise/scenario-c/preview`, and required for saved instances, history, baselines, and idempotency. Use `/health/ready` to verify database revision and A/B/C solver availability separately from database readiness. Do not expose demo identity authentication in production. Retain bounded request sizes, solver limits, one worker, and the rich-validation publication gate.
