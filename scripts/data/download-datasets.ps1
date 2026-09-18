param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT,
    [switch]$PrepareOnly,
    [switch]$CheckSpace
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}
$requiredBytes = [int64]7076266673
$minimumFreeBytes = [int64](20GB)

$directories = @(
    'archives', 'raw', 'processed', 'samples', 'manifests', 'checksums', 'logs',
    'raw\vegetable-disease-kg', 'raw\agricultural-knowledge',
    'raw\tomato-multimodal', 'raw\tomato-leaf-disease',
    'raw\rice-phenology', 'raw\crop-phenology-images'
)

foreach ($relativePath in $directories) {
    $path = Join-Path $DataRoot $relativePath
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

$manifestSource = Join-Path $PSScriptRoot '..\..\config\datasets\agrigraph-datasets.json'
$manifestTarget = Join-Path $DataRoot 'manifests\agrigraph-datasets.json'
Copy-Item -LiteralPath $manifestSource -Destination $manifestTarget -Force

if ($CheckSpace) {
    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($DataRoot).TrimEnd(':\'))
    $freeBytes = [int64]$drive.Free
    Write-Host ("Data root: {0}" -f $DataRoot)
    Write-Host ("Free space: {0:N2} GiB" -f ($freeBytes / 1GB))
    Write-Host ("Recommended reserve: {0:N2} GiB" -f ($minimumFreeBytes / 1GB))
    if ($freeBytes -lt $minimumFreeBytes) {
        throw 'Less than 20 GiB free space is available. Download stopped.'
    }
}

Write-Host ("AgriGraph data directories are ready: {0}" -f $DataRoot)
Write-Host ("Recommended dataset size: {0:N2} GiB" -f ($requiredBytes / 1GB))

if ($PrepareOnly) {
    Write-Host 'Prepare-only mode: no raw data was downloaded.'
    exit 0
}

Write-Host 'ScienceDB files require a public download link or an authenticated browser session.'
Write-Host 'Put downloaded archives under archives and calculate checksums with:'
Write-Host "Get-ChildItem '$DataRoot\archives' -File | Get-FileHash -Algorithm SHA256 | Format-Table"
Write-Host 'Keep raw files unchanged. Extraction and conversion scripts write to processed.'
