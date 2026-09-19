#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 1 || -z "${1:-}" ]]; then
  echo "Usage: $0 PROJECT_ID [REGION] [ZONE]" >&2
  exit 2
fi

PROJECT_ID="$1"
REGION="${2:-us-central1}"
ZONE="${3:-${REGION}-a}"
REPOSITORY="railplan"
BACKEND_SERVICE="railplan-api"
FRONTEND_SERVICE="railplan-web"
TAG="$(date -u +%Y%m%d%H%M%S)"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
BACKEND_IMAGE="${REGISTRY}/backend:${TAG}"
FRONTEND_IMAGE="${REGISTRY}/frontend:${TAG}"
PENDING_CORS_ORIGIN="https://pending.invalid"

for command_name in gcloud curl; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
done

check_url() {
  local url="$1"
  local label="$2"
  echo "Checking ${label}: ${url}"
  curl --fail --silent --show-error \
    --retry 12 --retry-delay 5 --retry-all-errors \
    --max-time 30 "${url}" >/dev/null
}

echo "Configuring project ${PROJECT_ID}, region ${REGION}, zone ${ZONE}"
gcloud config set project "${PROJECT_ID}" --quiet
gcloud config set run/region "${REGION}" --quiet
gcloud config set compute/zone "${ZONE}" --quiet

echo "Enabling Cloud Run, Cloud Build, and Artifact Registry APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project "${PROJECT_ID}" \
  --quiet

if gcloud artifacts repositories describe "${REPOSITORY}" \
  --project "${PROJECT_ID}" --location "${REGION}" >/dev/null 2>&1; then
  echo "Reusing Artifact Registry repository ${REPOSITORY}"
else
  echo "Creating Artifact Registry repository ${REPOSITORY}"
  gcloud artifacts repositories create "${REPOSITORY}" \
    --project "${PROJECT_ID}" \
    --location "${REGION}" \
    --repository-format docker \
    --description "RailPlan Cloud Run images" \
    --quiet
fi

echo "Building backend image ${BACKEND_IMAGE}"
gcloud builds submit . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --config deploy/gcp/cloudbuild.backend.yaml \
  --substitutions "_IMAGE=${BACKEND_IMAGE}" \
  --quiet

echo "Deploying stateless backend"
gcloud run deploy "${BACKEND_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --image "${BACKEND_IMAGE}" \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 2 \
  --memory 4Gi \
  --concurrency 1 \
  --max-instances 1 \
  --timeout 900 \
  --set-env-vars "RAILPLAN_RUN_MIGRATIONS=0,RAILPLAN_REQUIRE_DATABASE=0,RAILPLAN_ENV=production,RAILPLAN_DEMO_AUTH=0,RAILPLAN_CORS_ORIGINS=${PENDING_CORS_ORIGIN}" \
  --quiet

BACKEND_URL="$(gcloud run services describe "${BACKEND_SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)')"
if [[ -z "${BACKEND_URL}" ]]; then
  echo "Cloud Run did not return a backend URL" >&2
  exit 1
fi

check_url "${BACKEND_URL}/health" "backend health"
check_url "${BACKEND_URL}/health/live" "backend liveness"
check_url "${BACKEND_URL}/health/ready" "backend readiness"

echo "Building frontend image ${FRONTEND_IMAGE} with API URL ${BACKEND_URL}"
gcloud builds submit . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --config deploy/gcp/cloudbuild.frontend.yaml \
  --substitutions "_IMAGE=${FRONTEND_IMAGE},_API_URL=${BACKEND_URL}" \
  --quiet

echo "Deploying frontend"
gcloud run deploy "${FRONTEND_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --image "${FRONTEND_IMAGE}" \
  --allow-unauthenticated \
  --port 8080 \
  --quiet

FRONTEND_URL="$(gcloud run services describe "${FRONTEND_SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)')"
if [[ -z "${FRONTEND_URL}" ]]; then
  echo "Cloud Run did not return a frontend URL" >&2
  exit 1
fi

echo "Restricting backend CORS to ${FRONTEND_URL}"
gcloud run services update "${BACKEND_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --set-env-vars "RAILPLAN_RUN_MIGRATIONS=0,RAILPLAN_REQUIRE_DATABASE=0,RAILPLAN_ENV=production,RAILPLAN_DEMO_AUTH=0,RAILPLAN_CORS_ORIGINS=${FRONTEND_URL}" \
  --quiet

check_url "${BACKEND_URL}/health" "final backend health"
check_url "${BACKEND_URL}/health/live" "final backend liveness"
check_url "${BACKEND_URL}/health/ready" "final backend readiness"
check_url "${FRONTEND_URL}" "frontend"

CORS_ORIGIN="$(curl --fail --silent --show-error \
  --retry 6 --retry-delay 5 --retry-all-errors \
  --max-time 30 -D - -o /dev/null \
  -H "Origin: ${FRONTEND_URL}" "${BACKEND_URL}/health" \
  | tr -d '\r' \
  | awk -F': ' 'tolower($1)=="access-control-allow-origin" {print $2; exit}')"
if [[ "${CORS_ORIGIN}" != "${FRONTEND_URL}" ]]; then
  echo "Backend CORS verification failed: expected ${FRONTEND_URL}, received ${CORS_ORIGIN:-<none>}" >&2
  exit 1
fi

printf '\nDeployment complete.\nBackend: %s\nFrontend: %s\n' "${BACKEND_URL}" "${FRONTEND_URL}"
