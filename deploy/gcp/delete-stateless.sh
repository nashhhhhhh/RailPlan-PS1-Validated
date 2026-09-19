#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 1 || -z "${1:-}" ]]; then
  echo "Usage: $0 PROJECT_ID [REGION]" >&2
  exit 2
fi

PROJECT_ID="$1"
REGION="${2:-us-central1}"
REPOSITORY="railplan"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Required command not found: gcloud" >&2
  exit 1
fi

delete_service() {
  local service="$1"
  if gcloud run services describe "${service}" \
    --project "${PROJECT_ID}" --region "${REGION}" >/dev/null 2>&1; then
    gcloud run services delete "${service}" \
      --project "${PROJECT_ID}" --region "${REGION}" --quiet
  else
    echo "Cloud Run service already absent: ${service}"
  fi
}

delete_service railplan-web
delete_service railplan-api

if gcloud artifacts repositories describe "${REPOSITORY}" \
  --project "${PROJECT_ID}" --location "${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories delete "${REPOSITORY}" \
    --project "${PROJECT_ID}" --location "${REGION}" --quiet
else
  echo "Artifact Registry repository already absent: ${REPOSITORY}"
fi

echo "Deleted RailPlan stateless Cloud Run services and Artifact Registry repository from ${PROJECT_ID}/${REGION}."
