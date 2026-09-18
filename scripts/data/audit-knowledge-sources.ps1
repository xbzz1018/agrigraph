param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}
$scanRoots = @(
    'raw\agriculture-text',
    'raw\agriculture-standards',
    'raw\agriculture-ontology'
)
$results = foreach ($relativeRoot in $scanRoots) {
    $root = Join-Path $DataRoot $relativeRoot
    if (-not (Test-Path -LiteralPath $root)) { continue }
    foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -File) {
        $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
        $header = [byte[]](Get-Content -LiteralPath $file.FullName -Encoding Byte -TotalCount 8 -ErrorAction SilentlyContinue)
        $isPdf = $header.Length -ge 4 -and [Text.Encoding]::ASCII.GetString($header, 0, 4) -eq '%PDF'
        $extensionMatches = if ($file.Extension -eq '.pdf') { $isPdf } else { $true }
        $manifest = Get-ChildItem -LiteralPath (Join-Path $DataRoot 'manifests') -Filter '*.json' -File -ErrorAction SilentlyContinue |
            Where-Object { (Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8) -match [regex]::Escape($file.Name) } |
            Select-Object -First 1
        [pscustomobject]@{
            file = $file.FullName
            bytes = $file.Length
            sha256 = $hash.Hash
            empty = $file.Length -eq 0
            extensionMatches = $extensionMatches
            manifestPresent = $null -ne $manifest
            status = if ($file.Length -eq 0) { '空文件' } elseif (-not $extensionMatches) { '格式不匹配' } elseif (-not $manifest) { '缺少来源清单' } else { '通过' }
        }
    }
}

$duplicates = $results | Group-Object sha256 | Where-Object Count -gt 1
$report = [pscustomobject]@{
    generatedAt = (Get-Date).ToString('o')
    totalFiles = @($results).Count
    passedFiles = @($results | Where-Object status -eq '通过').Count
    duplicateGroups = @($duplicates).Count
    files = @($results)
}
$reportPath = Join-Path $DataRoot ('logs\knowledge-source-audit-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$results | Format-Table status, bytes, file -AutoSize
Write-Host "检测报告：$reportPath"
