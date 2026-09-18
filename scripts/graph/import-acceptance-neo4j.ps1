param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dataRootPath = (Resolve-Path -LiteralPath $DataRoot).Path
$nodesPath = (Resolve-Path -LiteralPath (Join-Path $dataRootPath 'processed\graph\nodes.csv')).Path
$edgesPath = (Resolve-Path -LiteralPath (Join-Path $dataRootPath 'processed\graph\edges.csv')).Path
$cypherPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'import-agrigraph.cypher')).Path
$verifyPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'verify-agrigraph.cypher')).Path
$composeFile = Join-Path $projectRoot 'compose.yml'
$envFile = Join-Path $projectRoot 'var\acceptance\infra.env'

foreach ($path in @($nodesPath, $edgesPath)) {
    if (-not $path.StartsWith($dataRootPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Import file escaped AGRIGRAPH_DATA_ROOT: $path"
    }
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Acceptance environment is missing. Start acceptance dependencies first.'
}

$composeProject = $env:AGRIGRAPH_COMPOSE_PROJECT
if ([string]::IsNullOrWhiteSpace($composeProject)) { $composeProject = 'agrigraph-evidence-v2' }
$containerId = (& docker compose --project-name $composeProject --env-file $envFile -f $composeFile ps -q neo4j).Trim()
if (-not $containerId) {
    throw 'The AgriGraph Neo4j acceptance container is not running.'
}

& docker exec $containerId sh -c 'mkdir -p /var/lib/neo4j/import/agrigraph'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& docker cp $nodesPath "${containerId}:/var/lib/neo4j/import/agrigraph/nodes.csv"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& docker cp $edgesPath "${containerId}:/var/lib/neo4j/import/agrigraph/edges.csv"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& docker cp $cypherPath "${containerId}:/var/lib/neo4j/import/agrigraph/import-agrigraph.cypher"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& docker cp $verifyPath "${containerId}:/var/lib/neo4j/import/agrigraph/verify-agrigraph.cypher"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& docker exec $containerId sh -c 'cypher-shell -a bolt://localhost:7687 -u neo4j -p "${NEO4J_AUTH#neo4j/}" --file /var/lib/neo4j/import/agrigraph/import-agrigraph.cypher'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& docker exec $containerId sh -c 'cypher-shell -a bolt://localhost:7687 -u neo4j -p "${NEO4J_AUTH#neo4j/}" --format plain --file /var/lib/neo4j/import/agrigraph/verify-agrigraph.cypher'
exit $LASTEXITCODE
