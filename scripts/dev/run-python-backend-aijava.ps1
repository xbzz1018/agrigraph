param(
    [int]$Port = 8188,
    [string]$EnvFilePath = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backendRoot = Join-Path $projectRoot "backend-python"
$condaExe = $env:AGRIGRAPH_CONDA_EXE

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) { return }
        $value = $parts[1].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$($parts[0].Trim())" -Value $value
    }
}

if ([string]::IsNullOrWhiteSpace($condaExe)) {
    $condaCommand = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($condaCommand) {
        $condaExe = $condaCommand.Source
    }
    else { throw "Conda was not found. Add it to PATH or set AGRIGRAPH_CONDA_EXE." }
}
elseif (-not (Test-Path -LiteralPath $condaExe)) {
    throw "AGRIGRAPH_CONDA_EXE does not point to a file: $condaExe"
}
elseif ([IO.Path]::GetExtension($condaExe) -ne ".exe") {
    throw "AGRIGRAPH_CONDA_EXE must point to conda.exe, not a batch wrapper: $condaExe"
}

Import-DotEnv (Join-Path $backendRoot ".env")
Import-DotEnv (Join-Path $projectRoot ".env.ai")
if ($EnvFilePath) { Import-DotEnv $EnvFilePath }

$env:AGRIGRAPH_PORT = [string]$Port
$env:PYTHONDONTWRITEBYTECODE = "1"
Set-Location $backendRoot

& $condaExe run -n AiJava --no-capture-output python -c "import os,sys; assert os.path.basename(sys.prefix).lower() == 'aijava', sys.prefix"
if ($LASTEXITCODE -ne 0) { throw 'The backend must run inside Conda environment AiJava.' }

Write-Host "Applying AgriGraph migrations in Conda env AiJava..." -ForegroundColor Cyan
& $condaExe run -n AiJava --no-capture-output python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Starting AgriGraph Evidence QA backend at http://127.0.0.1:$Port" -ForegroundColor Cyan
& $condaExe run -n AiJava --no-capture-output python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
