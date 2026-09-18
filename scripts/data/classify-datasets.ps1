param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}
$archiveRoot = Join-Path $DataRoot 'archives'
$checksumRoot = Join-Path $DataRoot 'checksums'
$logRoot = Join-Path $DataRoot 'logs'

if (-not (Test-Path -LiteralPath $archiveRoot)) {
    throw "Archive directory does not exist: $archiveRoot"
}

New-Item -ItemType Directory -Force -Path $checksumRoot, $logRoot | Out-Null

$rules = @(
    @{ Pattern = 'vegetable|disease.*knowledge|knowledge.*graph|neo4j'; Target = 'vegetable-disease-kg' },
    @{ Pattern = 'agricultural.*knowledge|preprocess|knowledge.*extract'; Target = 'agricultural-knowledge' },
    @{ Pattern = 'multimodal.*tomato|tomato.*multimodal'; Target = 'tomato-multimodal' },
    @{ Pattern = 'tomato.*leaf|leaf.*disease'; Target = 'tomato-leaf-disease' },
    @{ Pattern = 'rice.*phenology|phenology.*rice'; Target = 'rice-phenology' },
    @{ Pattern = 'crop.*phenology|phenology.*image|phenological.*phase'; Target = 'crop-phenology-images' }
)

$sizeRules = @{
    '555476' = 'vegetable-disease-kg'
    '1557052' = 'agricultural-knowledge'
    '1922321179' = 'tomato-multimodal'
    '1479093899' = 'tomato-leaf-disease'
    '1476043519' = 'rice-phenology'
    '2196695548' = 'crop-phenology-images'
}

$archives = Get-ChildItem -LiteralPath $archiveRoot -File
if (-not $archives) {
    Write-Host "No archive found in $archiveRoot"
    exit 0
}

foreach ($archive in $archives) {
    if ($archive.Extension -eq '.crdownload' -or $archive.Name -like '*.part') {
        Write-Warning "Skipping incomplete browser download: $($archive.Name)"
        continue
    }

    $rule = $rules | Where-Object { $archive.BaseName -match $_.Pattern } | Select-Object -First 1
    if (-not $rule -and $sizeRules.ContainsKey([string]$archive.Length)) {
        $rule = @{ Target = $sizeRules[[string]$archive.Length] }
    }
    if (-not $rule) {
        Write-Warning "Cannot classify archive: $($archive.Name)"
        continue
    }

    $target = Join-Path $DataRoot ("raw\" + $rule.Target)
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $hash = Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256
    $hashRecord = [pscustomobject]@{
        file = $archive.Name
        dataset = $rule.Target
        bytes = $archive.Length
        sha256 = $hash.Hash
        classifiedAt = (Get-Date).ToString('o')
    }
    $hashPath = Join-Path $checksumRoot ($archive.Name + '.json')
    $hashRecord | ConvertTo-Json | Set-Content -LiteralPath $hashPath -Encoding UTF8

    $isCompressedArchive = $archive.Extension -in @('.zip', '.rar')
    $completionMarker = Join-Path $target ('.agrigraph-extracted-' + $archive.Name + '.json')
    if ($isCompressedArchive -and (Test-Path -LiteralPath $completionMarker)) {
        Write-Host ("Skipping extracted archive: {0}" -f $archive.Name)
        continue
    }

    if ($isCompressedArchive) {
        # Windows 自带 tar 对大量小文件的 ZIP/RAR 解压更稳定，且不会额外启动后台进程。
        & tar -xf $archive.FullName -C $target
        if ($LASTEXITCODE -ne 0) {
            throw "Archive extraction failed: $($archive.Name)"
        }
        [pscustomobject]@{
            file = $archive.Name
            sha256 = $hash.Hash
            extractedAt = (Get-Date).ToString('o')
        } | ConvertTo-Json | Set-Content -LiteralPath $completionMarker -Encoding UTF8
    } elseif ($archive.Extension -eq '.7z') {
        Write-Warning "7z archive requires a 7-Zip executable: $($archive.Name)"
        continue
    } else {
        Copy-Item -LiteralPath $archive.FullName -Destination (Join-Path $target $archive.Name) -Force
    }
    Write-Host ("Classified {0} -> raw\{1}" -f $archive.Name, $rule.Target)
}

Write-Host 'Classification complete.'
