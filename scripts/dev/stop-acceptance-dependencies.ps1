$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeFile = Join-Path $projectRoot "compose.yml"
$envFile = Join-Path $projectRoot "var\acceptance\infra.env"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "var\acceptance\infra.env does not exist; acceptance dependencies were not initialized."
}

$composeProject = $env:AGRIGRAPH_COMPOSE_PROJECT
if ([string]::IsNullOrWhiteSpace($composeProject)) { $composeProject = 'agrigraph-evidence-v2' }
& docker compose --project-name $composeProject --env-file $envFile -f $composeFile stop
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Acceptance dependencies stopped; Docker volumes were preserved." -ForegroundColor Green
