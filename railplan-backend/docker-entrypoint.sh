#!/bin/sh
set -eu

if [ "${RAILPLAN_RUN_MIGRATIONS:-1}" = "1" ]; then
  python -m alembic upgrade head
fi

exec python -m uvicorn app.main:app \
  --host "${RAILPLAN_HOST:-0.0.0.0}" \
  --port "${RAILPLAN_PORT:-8000}" \
  --workers "${RAILPLAN_API_WORKERS:-1}" \
  --proxy-headers
