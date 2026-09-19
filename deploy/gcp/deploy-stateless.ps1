[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ProjectId,

    [ValidateNotNullOrEmpty()]
    [string]$Region = "us-central1",

    [string]$Zone
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $Zone) {
    $Zone = "${Region}-a"
}

$Repository = "railplan"
$BackendService = "railplan-api"
$FrontendService = "railplan-web"
$Tag = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
$Registry = "$Region-docker.pkg.dev/$ProjectId/$Repository"
$BackendImage = "$Registry/backend:$Tag"
$FrontendImage = "$Registry/frontend:$Tag"
$PendingCorsOrigin = "https://pending.invalid"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "Required command not found: gcloud"
}

function Invoke-Gcloud {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed with exit code $LASTEXITCODE`: gcloud $($Arguments -join ' ')"
    }
}

function Get-GcloudValue {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $value = (& gcloud @Arguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed with exit code $LASTEXITCODE`: gcloud $($Arguments -join ' ')"
    }
    return $value
}

function Test-Url {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Label
    )

    Write-Host "Checking $Label`: $Url"
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 30 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        }
        catch {
            if ($attempt -eq 12) {
                throw "Health check failed for $Label at $Url after 12 attempts: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds 5
        }
    }
    throw "Health check failed for $Label at $Url"
}

Write-Host "Configuring project $ProjectId, region $Region, zone $Zone"
Invoke-Gcloud -Arguments @("config", "set", "project", $ProjectId, "--quiet")
Invoke-Gcloud -Arguments @("config", "set", "run/region", $Region, "--quiet")
Invoke-Gcloud -Arguments @("config", "set", "compute/zone", $Zone, "--quiet")

Write-Host "Enabling Cloud Run, Cloud Build, and Artifact Registry APIs"
Invoke-Gcloud -Arguments @(
    "services", "enable",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "--project", $ProjectId,
    "--quiet"
)

& gcloud artifacts repositories describe $Repository --project $ProjectId --location $Region *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Reusing Artifact Registry repository $Repository"
}
else {
    Write-Host "Creating Artifact Registry repository $Repository"
    Invoke-Gcloud -Arguments @(
        "artifacts", "repositories", "create", $Repository,
        "--project", $ProjectId,
        "--location", $Region,
        "--repository-format", "docker",
        "--description", "RailPlan Cloud Run images",
        "--quiet"
    )
}

Write-Host "Building backend image $BackendImage"
Invoke-Gcloud -Arguments @(
    "builds", "submit", ".",
    "--project", $ProjectId,
    "--region", $Region,
    "--config", "deploy/gcp/cloudbuild.backend.yaml",
    "--substitutions", "_IMAGE=$BackendImage",
    "--quiet"
)

Write-Host "Deploying stateless backend"
Invoke-Gcloud -Arguments @(
    "run", "deploy", $BackendService,
    "--project", $ProjectId,
    "--region", $Region,
    "--platform", "managed",
    "--image", $BackendImage,
    "--allow-unauthenticated",
    "--port", "8080",
    "--cpu", "2",
    "--memory", "4Gi",
    "--concurrency", "1",
    "--max-instances", "1",
    "--timeout", "900",
    "--set-env-vars", "RAILPLAN_RUN_MIGRATIONS=0,RAILPLAN_REQUIRE_DATABASE=0,RAILPLAN_ENV=production,RAILPLAN_DEMO_AUTH=0,RAILPLAN_CORS_ORIGINS=$PendingCorsOrigin",
    "--quiet"
)

$BackendUrl = Get-GcloudValue -Arguments @(
    "run", "services", "describe", $BackendService,
    "--project", $ProjectId,
    "--region", $Region,
    "--format=value(status.url)"
)
if (-not $BackendUrl) {
    throw "Cloud Run did not return a backend URL"
}

Test-Url -Url "$BackendUrl/health" -Label "backend health"
Test-Url -Url "$BackendUrl/health/live" -Label "backend liveness"
Test-Url -Url "$BackendUrl/health/ready" -Label "backend readiness"

Write-Host "Building frontend image $FrontendImage with API URL $BackendUrl"
Invoke-Gcloud -Arguments @(
    "builds", "submit", ".",
    "--project", $ProjectId,
    "--region", $Region,
    "--config", "deploy/gcp/cloudbuild.frontend.yaml",
    "--substitutions", "_IMAGE=$FrontendImage,_API_URL=$BackendUrl",
    "--quiet"
)

Write-Host "Deploying frontend"
Invoke-Gcloud -Arguments @(
    "run", "deploy", $FrontendService,
    "--project", $ProjectId,
    "--region", $Region,
    "--platform", "managed",
    "--image", $FrontendImage,
    "--allow-unauthenticated",
    "--port", "8080",
    "--quiet"
)

$FrontendUrl = Get-GcloudValue -Arguments @(
    "run", "services", "describe", $FrontendService,
    "--project", $ProjectId,
    "--region", $Region,
    "--format=value(status.url)"
)
if (-not $FrontendUrl) {
    throw "Cloud Run did not return a frontend URL"
}

Write-Host "Restricting backend CORS to $FrontendUrl"
Invoke-Gcloud -Arguments @(
    "run", "services", "update", $BackendService,
    "--project", $ProjectId,
    "--region", $Region,
    "--set-env-vars", "RAILPLAN_RUN_MIGRATIONS=0,RAILPLAN_REQUIRE_DATABASE=0,RAILPLAN_ENV=production,RAILPLAN_DEMO_AUTH=0,RAILPLAN_CORS_ORIGINS=$FrontendUrl",
    "--quiet"
)

Test-Url -Url "$BackendUrl/health" -Label "final backend health"
Test-Url -Url "$BackendUrl/health/live" -Label "final backend liveness"
Test-Url -Url "$BackendUrl/health/ready" -Label "final backend readiness"
Test-Url -Url $FrontendUrl -Label "frontend"

$corsResponse = Invoke-WebRequest -Uri "$BackendUrl/health" -Method Get -Headers @{ Origin = $FrontendUrl } -TimeoutSec 30 -UseBasicParsing
$corsOrigin = [string]$corsResponse.Headers["Access-Control-Allow-Origin"]
if ($corsOrigin -ne $FrontendUrl) {
    throw "Backend CORS verification failed: expected $FrontendUrl, received $corsOrigin"
}

Write-Host ""
Write-Host "Deployment complete."
Write-Host "Backend: $BackendUrl"
Write-Host "Frontend: $FrontendUrl"
