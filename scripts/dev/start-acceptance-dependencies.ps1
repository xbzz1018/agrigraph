param(
    [ValidateRange(30, 3600)]
    [int]$WaitTimeoutSeconds = 600,
    [ValidateRange(1, 65535)]
    [int]$ElasticsearchPort = 29200,
    [ValidateRange(1, 65535)]
    [int]$Neo4jHttpPort = 27474,
    [ValidateRange(1, 65535)]
    [int]$Neo4jBoltPort = 27687,
    [ValidateRange(1, 65535)]
    [int]$PostgreSqlPort = 25432,
    [ValidateRange(1, 65535)]
    [int]$RedisPort = 26379,
    [string]$ComposeProject = 'agrigraph-evidence-v2'
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeFile = Join-Path $projectRoot "compose.yml"
$runtimeDir = Join-Path $projectRoot "var\acceptance"
$envFile = Join-Path $runtimeDir "infra.env"

if (-not (Test-Path -LiteralPath $runtimeDir)) {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $envFile)) {
    $bytes = New-Object byte[] 24
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($bytes)
    }
    finally {
        $random.Dispose()
    }
    $secret = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "A").Replace("/", "B")
    $values = @(
        "AGRIGRAPH_NEO4J_USERNAME=neo4j",
        "AGRIGRAPH_NEO4J_PASSWORD=$secret",
        "NEO4J_PASSWORD=$secret",
        "POSTGRES_PASSWORD=$secret",
        "REDIS_PASSWORD=$secret",
        "PAISMART_JWT_SECRET=$secret"
    )
    [IO.File]::WriteAllLines($envFile, $values, [Text.UTF8Encoding]::new($false))
    Write-Host "Generated ignored local credentials at var\acceptance\infra.env." -ForegroundColor Yellow
}

$existingLines = [Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object { $existingLines.Add($_) }
foreach ($requiredSecret in @('POSTGRES_PASSWORD', 'REDIS_PASSWORD')) {
    if (-not ($existingLines | Where-Object { ($_ -split '=', 2)[0].Trim() -eq $requiredSecret })) {
        $bytes = New-Object byte[] 24
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $random.GetBytes($bytes) }
        finally { $random.Dispose() }
        $generated = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "A").Replace("/", "B")
        $existingLines.Add("$requiredSecret=$generated")
    }
}
[IO.File]::WriteAllLines($envFile, [string[]]$existingLines, [Text.UTF8Encoding]::new($false))

$secretValues = @{}
$existingLines | ForEach-Object {
    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2) { $secretValues[$parts[0].Trim()] = $parts[1] }
}

# Keep generated credentials while replacing script-managed connection values.
$managedValues = New-Object System.Collections.Specialized.OrderedDictionary
$managedValues.Add('AGRIGRAPH_ES_HOST_PORT', [string]$ElasticsearchPort)
$managedValues.Add('AGRIGRAPH_ES_URL', "http://127.0.0.1:$ElasticsearchPort")
$managedValues.Add('AGRIGRAPH_ES_INDEX', 'agrigraph_evidence_v2')
$managedValues.Add('AGRIGRAPH_COMPOSE_PROJECT', $ComposeProject)
$managedValues.Add('AGRIGRAPH_NEO4J_HTTP_HOST_PORT', [string]$Neo4jHttpPort)
$managedValues.Add('AGRIGRAPH_NEO4J_BOLT_HOST_PORT', [string]$Neo4jBoltPort)
$managedValues.Add('AGRIGRAPH_NEO4J_URL', "bolt://127.0.0.1:$Neo4jBoltPort")
$managedValues.Add('AGRIGRAPH_POSTGRES_HOST_PORT', [string]$PostgreSqlPort)
$managedValues.Add('AGRIGRAPH_POSTGRES_DSN', "postgresql://agrigraph:$($secretValues['POSTGRES_PASSWORD'])@127.0.0.1:$PostgreSqlPort/agrigraph_memory")
$managedValues.Add('AGRIGRAPH_REDIS_HOST_PORT', [string]$RedisPort)
$managedValues.Add('AGRIGRAPH_REDIS_URL', "redis://:$($secretValues['REDIS_PASSWORD'])@127.0.0.1:$RedisPort/0")
$preservedLines = [Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
    $key = ($_ -split '=', 2)[0].Trim()
    if (-not $managedValues.Contains($key)) { $preservedLines.Add($_) }
}
foreach ($entry in $managedValues.GetEnumerator()) {
    $preservedLines.Add("$($entry.Key)=$($entry.Value)")
}
[IO.File]::WriteAllLines($envFile, [string[]]$preservedLines, [Text.UTF8Encoding]::new($false))

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found on PATH."
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker engine is not available."
}

Write-Host "Starting AgriGraph acceptance dependencies..." -ForegroundColor Cyan
& docker compose --project-name $ComposeProject --env-file $envFile -f $composeFile up -d --wait --wait-timeout $WaitTimeoutSeconds
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Acceptance dependencies are healthy." -ForegroundColor Green
Write-Host "The application launcher will load var\acceptance\infra.env after .env.ai."
Write-Host "Elasticsearch: http://127.0.0.1:$ElasticsearchPort"
Write-Host "Neo4j Browser: http://127.0.0.1:$Neo4jHttpPort"
Write-Host "PostgreSQL: 127.0.0.1:$PostgreSqlPort"
Write-Host "Redis: 127.0.0.1:$RedisPort"
