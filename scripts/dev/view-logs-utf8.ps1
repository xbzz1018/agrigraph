$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
chcp 65001 > $null

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$logDir = Join-Path $projectRoot "logs"

Write-Host "Reading UTF-8 logs from $logDir" -ForegroundColor Cyan

if (-not (Test-Path $logDir)) {
    Write-Host "Log directory not found." -ForegroundColor Yellow
    exit 1
}

$files = Get-ChildItem $logDir -File | Sort-Object LastWriteTime -Descending

if (-not $files) {
    Write-Host "No log files found." -ForegroundColor Yellow
    exit 0
}

$files | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize

$latest = $files[0]
Write-Host ""
Write-Host "Latest log: $($latest.FullName)" -ForegroundColor Cyan
Write-Host ""

Get-Content -LiteralPath $latest.FullName -Encoding UTF8 -Tail 80
