# Stateless Google Cloud Run deployment

This deployment runs the RailPlan frontend and FastAPI backend as two public Cloud Run services. It targets `us-central1`; the helper scripts also set the default compute zone to `us-central1-a`. Cloud Run is regional, so the zone setting does not pin an individual Cloud Run instance.

The backend runs without PostgreSQL, migrations, or demo authentication. It exposes the stateless dataset validation and Scenario A, B, and C preview APIs. Persisted instances, saved optimisation runs, asynchronous persisted jobs, audit history, and operator-scoped storage require the separate PostgreSQL deployment.

## Prerequisites

- A Google Cloud project with billing enabled.
- Google Cloud CLI (`gcloud`) authenticated to an account that can enable services, submit Cloud Builds, create Artifact Registry repositories, deploy public Cloud Run services, and act as the runtime service account.
- Bash plus `curl`, or PowerShell 7 or Windows PowerShell 5.1.
- Repository root as the working directory.

Typical IAM roles are Service Usage Admin, Cloud Build Editor, Artifact Registry Administrator, Cloud Run Admin, and Service Account User. Organisation policies may require an administrator to grant the Cloud Build service account Artifact Registry write permission or to permit unauthenticated Cloud Run access.

No deployment secret is read or written by these scripts. The source upload excludes environment files, credentials, dependencies, virtual environments, build output, caches, logs, screenshots, database volumes, and ZIP files.

## Deploy from Cloud Shell

Open [Google Cloud Shell](https://shell.cloud.google.com/), clone or upload this repository, and run:

```bash
cd RailPlan-PS1-Validated
chmod +x deploy/gcp/*.sh
./deploy/gcp/deploy-stateless.sh YOUR_PROJECT_ID
```

The complete Bash form is:

```bash
./deploy/gcp/deploy-stateless.sh PROJECT_ID [REGION] [ZONE]
```

Defaults are `us-central1` and `${REGION}-a`. For the requested target, the exact command is:

```bash
./deploy/gcp/deploy-stateless.sh YOUR_PROJECT_ID us-central1 us-central1-a
```

From PowerShell:

```powershell
.\deploy\gcp\deploy-stateless.ps1 `
  -ProjectId YOUR_PROJECT_ID `
  -Region us-central1 `
  -Zone us-central1-a
```

An explicit project ID is mandatory. The scripts perform these operations in order:

1. Select the project, region, and default compute zone.
2. Enable Cloud Run, Cloud Build, and Artifact Registry.
3. Create or reuse the regional Docker repository `railplan`.
4. Build and deploy `railplan-api` with the required stateless environment.
5. verify `/health`, `/health/live`, and `/health/ready`.
6. Build `railplan-web` with the deployed API URL embedded as `NEXT_PUBLIC_RAILPLAN_API_URL`.
7. Deploy the frontend, then create a new backend revision whose CORS origin is the exact frontend URL.
8. Repeat the backend health checks, check the frontend root, verify the CORS response header, and print both public URLs.

The backend service uses two CPUs, 4 GiB memory, concurrency `1`, a maximum of one instance, and a 900-second request timeout. It receives:

```text
RAILPLAN_RUN_MIGRATIONS=0
RAILPLAN_REQUIRE_DATABASE=0
RAILPLAN_ENV=production
RAILPLAN_DEMO_AUTH=0
```

## CORS

The initial backend revision uses the inert exact origin `https://pending.invalid`. After the frontend is deployed, the script replaces that value with the frontend Cloud Run URL and checks that the backend returns the same value in `Access-Control-Allow-Origin`. Wildcard CORS is never configured.

If a custom domain is later attached to the frontend, update the backend to that exact origin and include the full stateless environment set:

```bash
gcloud run services update railplan-api \
  --project YOUR_PROJECT_ID \
  --region us-central1 \
  --set-env-vars "RAILPLAN_RUN_MIGRATIONS=0,RAILPLAN_REQUIRE_DATABASE=0,RAILPLAN_ENV=production,RAILPLAN_DEMO_AUTH=0,RAILPLAN_CORS_ORIGINS=https://railplan.example.com"
```

Origins contain scheme and hostname only. Do not add a trailing slash or use `*`.

## Health checks

Replace `BACKEND_URL` with the printed backend URL:

```bash
curl --fail --show-error BACKEND_URL/health
curl --fail --show-error BACKEND_URL/health/live
curl --fail --show-error BACKEND_URL/health/ready
```

Readiness should report `"mode":"stateless"`. The frontend can be checked with:

```bash
curl --fail --show-error FRONTEND_URL
```

## Logs

```bash
gcloud run services logs read railplan-api \
  --project YOUR_PROJECT_ID --region us-central1 --limit 100

gcloud run services logs read railplan-web \
  --project YOUR_PROJECT_ID --region us-central1 --limit 100
```

Use `--log-filter='severity>=ERROR'` to focus on failures.

## Revise a deployment

Commit the desired source revision and rerun the same deployment command. Each run uses a new timestamped backend and frontend image tag. The frontend must be rebuilt whenever the backend URL changes because `NEXT_PUBLIC_RAILPLAN_API_URL` is compiled into the browser bundle.

To inspect revisions:

```bash
gcloud run revisions list --service railplan-api --project YOUR_PROJECT_ID --region us-central1
gcloud run revisions list --service railplan-web --project YOUR_PROJECT_ID --region us-central1
```

## Roll back

Choose a revision from the list and send all traffic to it:

```bash
gcloud run services update-traffic railplan-api \
  --project YOUR_PROJECT_ID --region us-central1 \
  --to-revisions BACKEND_REVISION=100

gcloud run services update-traffic railplan-web \
  --project YOUR_PROJECT_ID --region us-central1 \
  --to-revisions FRONTEND_REVISION=100
```

Roll back both services as a compatible pair. Recheck the frontend build-time API URL and backend CORS origin after any rollback.

## Delete resources

The delete helpers remove both Cloud Run services and the `railplan` Artifact Registry repository, including its stored images:

```bash
./deploy/gcp/delete-stateless.sh YOUR_PROJECT_ID us-central1
```

```powershell
.\deploy\gcp\delete-stateless.ps1 -ProjectId YOUR_PROJECT_ID -Region us-central1
```

The enabled Google APIs, Cloud Build history, and Cloud Logging entries remain in the project.

## Cost warning

Cloud Build minutes, Artifact Registry storage, Cloud Run CPU, memory, network egress, and logs can incur charges. The backend is intentionally capped at one instance and no minimum instance count is requested, but a long optimiser request can use two CPUs and 4 GiB for up to 900 seconds. Delete the services and repository when the deployment is no longer needed. Billing and free-tier eligibility depend on the Google Cloud account and region.

## Stateless limitations

- No PostgreSQL database is provisioned or required.
- Migrations do not run.
- Demo identity headers are disabled in production.
- Saved instances, persisted validation history, saved optimisation runs, asynchronous persisted jobs, cancellation state, audit records, and operator isolation storage are unavailable.
- Container filesystem changes are temporary and may disappear whenever Cloud Run replaces an instance.
- The service maximum of one instance limits parallel capacity; concurrency `1` keeps solver requests isolated within that instance.
- The public endpoints receive no application login in this mode. Use IAM or an authenticated gateway before deploying private datasets.

The stateless Scenario A/B/C preview routes remain available. Each request must carry its input files and options.

## Scenario C `UNKNOWN`

`UNKNOWN` means the configured solve budget ended without an incumbent. It does not prove infeasibility. Treat the response as diagnostic, keep `judge_validation="not_run"` and `score_verification="internal_only"`, and do not publish or fabricate CSV output. A caller may retry with a realistic bounded time limit, but the request must complete within Cloud Run's 900-second timeout. Only candidates marked publishable and passing the rich physical validator should be used as generated schedules.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common build, IAM, startup, CORS, and timeout failures.
