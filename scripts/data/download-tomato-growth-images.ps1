param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$condaExe = $env:AGRIGRAPH_CONDA_EXE
if ([string]::IsNullOrWhiteSpace($condaExe)) {
    $condaCommand = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($condaCommand) {
        $condaExe = $condaCommand.Source
    }
    else { throw 'Conda was not found. Add it to PATH or set AGRIGRAPH_CONDA_EXE.' }
}
elseif (-not (Test-Path -LiteralPath $condaExe)) {
    throw "AGRIGRAPH_CONDA_EXE does not point to a file: $condaExe"
}
elseif ([IO.Path]::GetExtension($condaExe) -ne '.exe') {
    throw "AGRIGRAPH_CONDA_EXE must point to conda.exe, not a batch wrapper: $condaExe"
}

$env:AGRIGRAPH_DATA_ROOT = $DataRoot
if ($Check) {
    & $condaExe run -n AiJava python --version
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}

& $condaExe run -n AiJava --no-capture-output python (Join-Path $PSScriptRoot 'download-tomato-growth-images.py')
if ($LASTEXITCODE -ne 0) {
    throw "番茄生育期图片下载失败，退出码：$LASTEXITCODE"
}
