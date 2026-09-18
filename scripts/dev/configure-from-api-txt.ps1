param(
    [Parameter(Mandatory = $true)]
    [string]$ApiFile,
    [string]$OutputFile = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($OutputFile)) {
    $OutputFile = Join-Path $projectRoot '.env.ai'
}
if (-not (Test-Path -LiteralPath $ApiFile)) {
    throw "API file does not exist: $ApiFile"
}

function Get-ValueAfterLabel([string[]]$Lines, [string]$Label, [int]$StartAt = 0) {
    for ($i = $StartAt; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match "(?i)^\s*$Label\s*[^A-Za-z0-9]+\s*(.+)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ''
}

$lines = @(Get-Content -LiteralPath $ApiFile -Encoding UTF8)
$vibeUrl = ''
$vibeKey = ''
$workspaceUrl = ''
$workspaceKey = ''
$lastGroup = ''
for ($i = 0; $i -lt $lines.Count; $i++) {
    $line = $lines[$i].Trim()
    if (-not $line) { continue }
    if ($line -match '(?i)deepseek') { $lastGroup = 'vibe' }
    # api.txt may still label the shared Alibaba account by its older embedding/rerank use.
    if ($line -match '(?i)embedding|rerank|qwen3|vision|workspace') { $lastGroup = 'workspace' }
    if ($line -match '(?i)^url\s*[^A-Za-z0-9]+\s*(https?://\S+)') {
        if ($lastGroup -eq 'vibe') { $vibeUrl = $Matches[1].Trim() }
        elseif ($lastGroup -eq 'workspace') { $workspaceUrl = $Matches[1].Trim() }
        continue
    }
    if ($line -match '(?i)^key\s*[^A-Za-z0-9]+\s*(\S+)') {
        if ($lastGroup -eq 'vibe') { $vibeKey = $Matches[1].Trim() }
        elseif ($lastGroup -eq 'workspace') { $workspaceKey = $Matches[1].Trim() }
    }
}
if ([string]::IsNullOrWhiteSpace($vibeUrl) -or [string]::IsNullOrWhiteSpace($vibeKey)) {
    throw 'Could not resolve the DeepSeek/VibeAPI URL and key from the API file.'
}
if ([string]::IsNullOrWhiteSpace($workspaceUrl) -or [string]::IsNullOrWhiteSpace($workspaceKey)) {
    throw 'Could not resolve the Alibaba Workspace URL and key from the API file.'
}

# VibeAPI 的 api.txt 只给根域名，OpenAI 兼容接口位于 /v1。
$vibeUri = [Uri]$vibeUrl
if ([string]::IsNullOrWhiteSpace($vibeUri.AbsolutePath) -or $vibeUri.AbsolutePath -eq '/') {
    $vibeUrl = $vibeUrl.TrimEnd('/') + '/v1'
}

$template = Get-Content -Raw -LiteralPath (Join-Path $projectRoot '.env.ai.example') -Encoding UTF8
$values = @{
    'GATEWAY_API_BASE' = $vibeUrl
    'GATEWAY_API_KEY' = $vibeKey
    'GATEWAY_MODEL' = 'deepseek-v4-flash'
    'VISION_API_BASE' = $workspaceUrl
    'VISION_API_KEY' = $workspaceKey
    'VISION_MODEL' = 'qwen3-vl-flash'
}
foreach ($entry in $values.GetEnumerator()) {
    $pattern = "(?m)^$([regex]::Escape($entry.Key))=.*$"
    $replacement = "$($entry.Key)=$($entry.Value)"
    if ($template -match $pattern) {
        $template = [regex]::Replace($template, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $replacement })
    } else {
        $template += "`r`n$replacement"
    }
}

[IO.File]::WriteAllText($OutputFile, $template, [Text.UTF8Encoding]::new($false))
Write-Host "Generated ignored configuration at $OutputFile. Secrets were not printed."
