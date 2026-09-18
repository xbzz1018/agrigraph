param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT,
    [string]$Version = "v1"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw "请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录"
}

$resolvedRoot = [System.IO.Path]::GetFullPath($DataRoot)
if (-not (Test-Path -LiteralPath $resolvedRoot -PathType Container)) {
    throw "数据目录不存在：$resolvedRoot"
}

$releaseRoot = Join-Path $resolvedRoot "release"
$coreRoot = Join-Path $releaseRoot "agrigraph-core-$Version"
$imageRoot = Join-Path $releaseRoot "agrigraph-demo-images-$Version"
$coreZip = Join-Path $releaseRoot "agrigraph-core-$Version.zip"
$imageZip = Join-Path $releaseRoot "agrigraph-demo-images-$Version.zip"

foreach ($target in @($coreRoot, $imageRoot)) {
    if (Test-Path -LiteralPath $target) {
        throw "目标目录已存在，请更换版本号或人工确认后处理：$target"
    }
}

New-Item -ItemType Directory -Force -Path $releaseRoot, $coreRoot, $imageRoot | Out-Null

function Copy-RelativeFile {
    param(
        [string]$RelativePath,
        [string]$DestinationRoot
    )

    $source = Join-Path $resolvedRoot ($RelativePath -replace "/", "\")
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "发布文件不存在：$source"
    }

    $destination = Join-Path $DestinationRoot ($RelativePath -replace "/", "\")
    $destinationDirectory = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$coreFiles = @(
    "processed/graph/nodes.csv",
    "processed/graph/edges.csv",
    "processed/graph/quality-report.json",
    "processed/knowledge/agriculture-entities.jsonl",
    "processed/knowledge/image-entity-map.jsonl",
    "processed/knowledge/plant-ontology.jsonl",
    "processed/knowledge/source-documents.jsonl",
    "processed/knowledge/supplemental-images.jsonl",
    "processed/knowledge/tomato-growth-images.jsonl"
)

foreach ($relativePath in $coreFiles) {
    Copy-RelativeFile -RelativePath $relativePath -DestinationRoot $coreRoot
}

foreach ($directory in @("manifests", "checksums")) {
    $sourceDirectory = Join-Path $resolvedRoot $directory
    if (Test-Path -LiteralPath $sourceDirectory) {
        Copy-Item -LiteralPath $sourceDirectory -Destination $coreRoot -Recurse
    }
}

$mapPath = Join-Path $resolvedRoot "processed\knowledge\image-entity-map.jsonl"
$mappedImages = @(
    Get-Content -LiteralPath $mapPath -Encoding UTF8 |
        ForEach-Object { $_ | ConvertFrom-Json } |
        Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.entityId) }
)

$filteredMapPath = Join-Path $imageRoot "image-entity-map.jsonl"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$filteredLines = @($mappedImages | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 12 })
[System.IO.File]::WriteAllLines($filteredMapPath, $filteredLines, $utf8NoBom)

foreach ($image in $mappedImages) {
    Copy-RelativeFile -RelativePath ([string]$image.thumbnailFile) -DestinationRoot $imageRoot
}

$readmeTemplate = Join-Path $PSScriptRoot "public-release-readme.md"
$readme = (Get-Content -Raw -Encoding UTF8 -LiteralPath $readmeTemplate).Replace("{{VERSION}}", $Version)
[System.IO.File]::WriteAllText((Join-Path $coreRoot "README.md"), $readme, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $imageRoot "README.md"), $readme, $utf8NoBom)

Compress-Archive -Path (Join-Path $coreRoot "*") -DestinationPath $coreZip -CompressionLevel Optimal -Force
Compress-Archive -Path (Join-Path $imageRoot "*") -DestinationPath $imageZip -CompressionLevel Optimal -Force

$checksums = @(
    foreach ($archive in @($coreZip, $imageZip)) {
        $hash = Get-FileHash -LiteralPath $archive -Algorithm SHA256
        "{0}  {1}" -f $hash.Hash.ToLowerInvariant(), (Split-Path -Leaf $archive)
    }
)
[System.IO.File]::WriteAllLines((Join-Path $releaseRoot "SHA256SUMS.txt"), $checksums, $utf8NoBom)

$summary = foreach ($archive in @($coreZip, $imageZip)) {
    $file = Get-Item -LiteralPath $archive
    [pscustomobject]@{
        File = $file.Name
        SizeMB = [math]::Round($file.Length / 1MB, 2)
        SHA256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$summary | Format-Table -AutoSize
