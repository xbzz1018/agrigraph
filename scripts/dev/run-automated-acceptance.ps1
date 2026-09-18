param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT,
    [string]$EvaluationUsername = 'agrigraph_acceptance',
    [ValidateRange(30, 3600)]
    [int]$RequestTimeoutSeconds = 600,
    [switch]$SkipQualityGates,
    [switch]$SkipDataRefresh,
    [switch]$SkipEvaluation,
    [switch]$KeepRunning
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backendRoot = Join-Path $projectRoot 'backend-python'
$frontendRoot = Join-Path $projectRoot 'frontend'
$envFile = Join-Path $projectRoot 'var\acceptance\infra.env'
$reportPath = Join-Path $projectRoot 'var\reports\multimodal-candidate-summary.json'
$condaExe = $env:AGRIGRAPH_CONDA_EXE
$started = $false

function Invoke-Checked([scriptblock]$Command, [string]$Label) {
    Write-Host "[acceptance] $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { return }
        Set-Item -Path "Env:$($parts[0].Trim())" -Value $parts[1].Trim().Trim('"').Trim("'")
    }
}

if ([string]::IsNullOrWhiteSpace($condaExe)) {
    $condaCommand = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($condaCommand) { $condaExe = $condaCommand.Source }
}
if (-not $condaExe -or -not (Test-Path -LiteralPath $condaExe) -or [IO.Path]::GetExtension($condaExe) -ne '.exe') {
    throw 'Conda was not found. Set AGRIGRAPH_CONDA_EXE to conda.exe.'
}
& $condaExe run -n AiJava --no-capture-output python -c "import os,sys; assert os.path.basename(sys.prefix).lower() == 'aijava', sys.prefix"
if ($LASTEXITCODE -ne 0) { throw 'Automated acceptance must run inside Conda environment AiJava.' }
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw 'Set -DataRoot or AGRIGRAPH_DATA_ROOT to the external AgriGraph data directory.'
}
if (-not (Test-Path -LiteralPath $DataRoot)) {
    throw "AGRIGRAPH_DATA_ROOT does not exist: $DataRoot"
}

$bytes = New-Object byte[] 18
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $random.GetBytes($bytes) } finally { $random.Dispose() }
$evaluationPassword = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', 'A').Replace('/', 'B')

try {
    if (-not $SkipQualityGates) {
        Push-Location $backendRoot
        Invoke-Checked { & $condaExe run --no-capture-output -n AiJava python -m ruff check app tests migrations } 'Backend Ruff'
        Invoke-Checked { & $condaExe run --no-capture-output -n AiJava python -m pytest tests } 'Backend tests'
        Invoke-Checked { & $condaExe run --no-capture-output -n AiJava python -m alembic upgrade head } 'Alembic upgrade'
        Pop-Location

        Push-Location $frontendRoot
        Invoke-Checked { & pnpm typecheck } 'Frontend typecheck'
        Invoke-Checked { & pnpm build } 'Frontend build'
        Pop-Location
    }

    Invoke-Checked { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-acceptance-dependencies.ps1') } 'Dependency startup'
    Import-DotEnv (Join-Path $projectRoot '.env.ai')
    Import-DotEnv $envFile
    $env:AGRIGRAPH_DATA_ROOT = $DataRoot

    Push-Location $backendRoot
    if (-not $SkipDataRefresh) {
        Invoke-Checked {
            & $condaExe run --no-capture-output -n AiJava python -m app.import_knowledge --data-root $DataRoot --env-file $envFile --recreate-index
        } 'Elasticsearch knowledge import'
    }
    $env:AGRIGRAPH_RESET_USERNAME = $EvaluationUsername
    $env:AGRIGRAPH_RESET_PASSWORD = $evaluationPassword
    Invoke-Checked {
        & $condaExe run --no-capture-output -n AiJava python -m app.reset_password --role ADMIN --create
    } 'Acceptance account recovery'
    Pop-Location

    if (-not $SkipDataRefresh) {
        Invoke-Checked {
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot 'scripts\graph\build-neo4j-import.ps1') -DataRoot $DataRoot
        } 'Neo4j import data rebuild'
        Invoke-Checked {
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot 'scripts\graph\import-acceptance-neo4j.ps1') -DataRoot $DataRoot
        } 'Neo4j knowledge import'
    }

    Push-Location $backendRoot
    Invoke-Checked {
        & $condaExe run --no-capture-output -n AiJava python -m app.cli.verify_data_baseline `
            --data-root $DataRoot --env-file $envFile --output (Join-Path $projectRoot 'var\reports\data-baseline-verification.json')
    } 'V2 data baseline verification'
    Invoke-Checked {
        & $condaExe run --no-capture-output -n AiJava python -m app.cli.preflight_models `
            --data-root $DataRoot --env-file $envFile --output (Join-Path $projectRoot 'var\reports\model-preflight.json')
    } 'DeepSeek and Qwen3-VL preflight'
    Pop-Location

    $started = $true
    Invoke-Checked { & cmd.exe /d /c (Join-Path $projectRoot 'start-windows.bat') } 'Application startup'
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/api/v1/health/dependencies' -TimeoutSec 30
    if ($health.data.status -ne 'UP') {
        throw "Dependency health is not UP: $($health.data.status)"
    }

    $env:AGRIGRAPH_EVAL_USERNAME = $EvaluationUsername
    $env:AGRIGRAPH_EVAL_PASSWORD = $evaluationPassword
    if (-not $SkipEvaluation) {
        Invoke-Checked {
            & $condaExe run --no-capture-output -n AiJava python scripts\evaluation\run-rag-evaluation.py `
                --data-root $DataRoot --request-timeout $RequestTimeoutSeconds --workers 2
        } 'Text, image, and control-relation evaluation'
        if (-not (Test-Path -LiteralPath $reportPath)) {
            throw 'Evaluation completed without the multimodal candidate summary.'
        }
        $report = Get-Content -Raw -Encoding UTF8 $reportPath | ConvertFrom-Json
        if ($report.status -ne 'COMPLETED_CANDIDATE' -or $report.releaseClass -ne 'CANDIDATE_NOT_FORMAL_RELEASE') {
            throw 'Evaluation candidate did not pass all frozen gates.'
        }
    }
    Write-Host '[acceptance] COMPLETED' -ForegroundColor Green
}
finally {
    Remove-Item Env:AGRIGRAPH_RESET_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:AGRIGRAPH_EVAL_PASSWORD -ErrorAction SilentlyContinue
    if (-not $KeepRunning) {
        if ($started) { & cmd.exe /d /c (Join-Path $projectRoot 'stop-windows.bat') | Out-Null }
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stop-acceptance-dependencies.ps1') | Out-Null
    }
}
