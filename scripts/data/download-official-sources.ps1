param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT,
    [string]$Manifest = $(Join-Path $PSScriptRoot '..\..\config\datasets\official-agriculture-sources.json')
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}
$manifestData = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$downloadLog = Join-Path $DataRoot ('logs\official-download-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
New-Item -ItemType Directory -Force -Path (Split-Path $downloadLog) | Out-Null

foreach ($source in $manifestData.sources) {
    if ([string]::IsNullOrWhiteSpace($source.downloadUrl)) {
        "跳过 $($source.id)：尚未审核下载直链。" | Tee-Object -FilePath $downloadLog -Append
        continue
    }
    if ($source.status -ne '已审核') {
        "跳过 $($source.id)：状态不是已审核。" | Tee-Object -FilePath $downloadLog -Append
        continue
    }

    $targetDirectory = Join-Path $DataRoot $source.targetDirectory
    New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
    $fileName = if ($source.fileName) { $source.fileName } else { [IO.Path]::GetFileName(([Uri]$source.downloadUrl).AbsolutePath) }
    if ([string]::IsNullOrWhiteSpace($fileName)) { throw "资料 $($source.id) 缺少 fileName。" }
    $targetFile = Join-Path $targetDirectory $fileName

    if (Test-Path -LiteralPath $targetFile) {
        "已存在，跳过：$targetFile" | Tee-Object -FilePath $downloadLog -Append
        continue
    }

    "正在下载：$($source.title)" | Tee-Object -FilePath $downloadLog -Append
    # 使用 Windows 自带 curl，兼容 PowerShell 5.1，并支持断点续传和失败重试。
    & curl.exe -L --fail --retry 3 --retry-delay 3 -C - --output $targetFile $source.downloadUrl
    if ($LASTEXITCODE -ne 0) { throw "资料下载失败：$($source.id)" }
    $hash = Get-FileHash -LiteralPath $targetFile -Algorithm SHA256
    [pscustomobject]@{
        id = $source.id
        title = $source.title
        publisher = $source.publishers
        sourceUrl = $source.sourceUrl
        downloadUrl = $source.downloadUrl
        license = $source.license
        localPath = $targetFile
        sizeBytes = (Get-Item -LiteralPath $targetFile).Length
        sha256 = $hash.Hash
        downloadedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path "$DataRoot\manifests" ($source.id + '.json')) -Encoding UTF8
}

Write-Host "官方资料下载处理完成，日志：$downloadLog"
