# Google Cloud Run troubleshooting

The deployment helpers stop on the first failed command. They do not report success or print service URLs until both services, backend health, frontend response, and exact CORS verification have passed.

## Confirm the active account and project

```bash
gcloud auth list
gcloud config get-value project
gcloud projects describe YOUR_PROJECT_ID
```

The deployment command always requires a project ID and passes it explicitly to build and service commands. Billing must be enabled on that project.

## API enablement or permission failure

Confirm the required services:

```bash
gcloud services list --enabled --project YOUR_PROJECT_ID \
  --filter='name:(run.googleapis.com OR cloudbuild.googleapis.com OR artifactregistry.googleapis.com)'
```

Permission errors commonly mean the caller cannot enable services, create the repository, submit builds, deploy Cloud Run, make a service public, or act as the runtime service account. Organisation policy may prohibit `--allow-unauthenticated`. Ask the project administrator for the required role or policy change; do not add credentials to the repository.

If Cloud Build cannot push an image, identify its service account from the failed build and grant it Artifact Registry Writer on the `railplan` repository according to your organisation's IAM policy.

## Inspect failed builds

```bash
gcloud builds list --project YOUR_PROJECT_ID --region us-central1 --limit 10
gcloud builds log BUILD_ID --project YOUR_PROJECT_ID --region us-central1
```

The backend build context is `railplan-backend`. The frontend uses the repository root, Node.js 22, Corepack, pnpm `11.25.0`, a frozen lockfile, and the standard `next build`. Wrangler is not used by the Cloud Run image.

If the frontend calls `127.0.0.1:8000` in a deployed browser, it was built without the correct `_API_URL`. Rebuild it through `cloudbuild.frontend.yaml` and confirm the build step contains:

```text
NEXT_PUBLIC_RAILPLAN_API_URL=https://...run.app
```

## Container does not listen on the assigned port

Cloud Run sets `PORT`, normally to `8080`. The backend entrypoint resolves `PORT`, then `RAILPLAN_PORT`, then `8000`. The frontend starts Next.js with `--hostname 0.0.0.0` and `${PORT:-8080}`.

Inspect the failed revision:

```bash
gcloud run services describe railplan-api --project YOUR_PROJECT_ID --region us-central1
gcloud run services logs read railplan-api --project YOUR_PROJECT_ID --region us-central1 --limit 100
```

For the frontend, replace `railplan-api` with `railplan-web`.

## Backend readiness returns 503

Inspect the deployed environment:

```bash
gcloud run services describe railplan-api \
  --project YOUR_PROJECT_ID --region us-central1 \
  --format='yaml(spec.template.spec.containers[0].env)'
```

The stateless revision must contain:

```text
RAILPLAN_RUN_MIGRATIONS=0
RAILPLAN_REQUIRE_DATABASE=0
RAILPLAN_ENV=production
RAILPLAN_DEMO_AUTH=0
```

Remove `DATABASE_URL` from a service that is intended to remain stateless. Readiness should then return `mode: stateless`. A persisted deployment has separate database, migration, security, and availability requirements.

## CORS failure

Get the current URLs:

```bash
BACKEND_URL=$(gcloud run services describe railplan-api --project YOUR_PROJECT_ID --region us-central1 --format='value(status.url)')
FRONTEND_URL=$(gcloud run services describe railplan-web --project YOUR_PROJECT_ID --region us-central1 --format='value(status.url)')
```

Inspect the response:

```bash
curl -i -H "Origin: ${FRONTEND_URL}" "${BACKEND_URL}/health"
```

`Access-Control-Allow-Origin` must equal the frontend URL exactly. Scheme, hostname, and any port must match; omit a trailing slash. The backend intentionally rejects wildcard CORS.

To repair it while preserving the stateless environment:

```bash
gcloud run services update railplan-api \
  --project YOUR_PROJECT_ID --region us-central1 \
  --set-env-vars "RAILPLAN_RUN_MIGRATIONS=0,RAILPLAN_REQUIRE_DATABASE=0,RAILPLAN_ENV=production,RAILPLAN_DEMO_AUTH=0,RAILPLAN_CORS_ORIGINS=${FRONTEND_URL}"
```

## Optimiser request times out

The backend Cloud Run request timeout is 900 seconds. Keep every solver time limit below that boundary so request parsing, validation, response serialization, and network overhead can complete. The service uses concurrency `1` and a maximum of one instance, so another long request waits or may be rejected by upstream limits.

Use a bounded realistic solver limit. For Scenario C, `UNKNOWN` means the solver reached its limit without an incumbent; it is distinct from `INFEASIBLE`. Do not create CSV files from an `UNKNOWN`, `INFEASIBLE`, or `MODEL_INVALID` result. Inspect diagnostics, retry only when useful, and accept output only when the response is publishable and its rich physical validation passes.

## Revisions and rollback

List traffic and revisions:

```bash
gcloud run services describe railplan-api --project YOUR_PROJECT_ID --region us-central1 --format='yaml(status.traffic)'
gcloud run revisions list --service railplan-api --project YOUR_PROJECT_ID --region us-central1
gcloud run revisions list --service railplan-web --project YOUR_PROJECT_ID --region us-central1
```

Move traffic to a known revision with `gcloud run services update-traffic SERVICE --to-revisions REVISION=100`. Roll back the backend and frontend as a pair, then verify all health URLs and exact CORS again.

## Partial deployment cleanup

If a deployment stopped after creating some resources, rerunning it is safe: the repository is reused and Cloud Run creates new revisions. To remove everything created for the stateless deployment:

```bash
./deploy/gcp/delete-stateless.sh YOUR_PROJECT_ID us-central1
```

This removes `railplan-api`, `railplan-web`, and the `railplan` image repository. It does not disable APIs or erase Cloud Build and Cloud Logging history.
