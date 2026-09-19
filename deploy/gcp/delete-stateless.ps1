[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ProjectId,

    [ValidateNotNullOrEmpty()]
    [string]$Region = "us-central1"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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

function Remove-CloudRunService {
    param([Parameter(Mandatory = $true)][string]$Service)
    & gcloud run services describe $Service --project $ProjectId --region $Region *> $null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Gcloud -Arguments @(
            "run", "services", "delete", $Service,
            "--project", $ProjectId,
            "--region", $Region,
            "--quiet"
        )
    }
    else {
        Write-Host "Cloud Run service already absent: $Service"
    }
}

Remove-CloudRunService -Service "railplan-web"
Remove-CloudRunService -Service "railplan-api"

& gcloud artifacts repositories describe railplan --project $ProjectId --location $Region *> $null
if ($LASTEXITCODE -eq 0) {
    Invoke-Gcloud -Arguments @(
        "artifacts", "repositories", "delete", "railplan",
        "--project", $ProjectId,
        "--location", $Region,
        "--quiet"
    )
}
else {
    Write-Host "Artifact Registry repository already absent: railplan"
}

Write-Host "Deleted RailPlan stateless Cloud Run services and Artifact Registry repository from $ProjectId/$Region."
