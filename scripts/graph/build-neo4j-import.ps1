param(
    [string]$DataRoot = $env:AGRIGRAPH_DATA_ROOT
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    throw '请通过 -DataRoot 或 AGRIGRAPH_DATA_ROOT 指定外部数据目录'
}
$condaExe = $env:AGRIGRAPH_CONDA_EXE
if ([string]::IsNullOrWhiteSpace($condaExe)) {
    $condaCommand = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $condaCommand) { throw 'Conda was not found. Add it to PATH or set AGRIGRAPH_CONDA_EXE.' }
    $condaExe = $condaCommand.Source
}
if (-not (Test-Path -LiteralPath $condaExe) -or [IO.Path]::GetExtension($condaExe) -ne '.exe') {
    throw 'AGRIGRAPH_CONDA_EXE must point to conda.exe.'
}

$env:AGRIGRAPH_DATA_ROOT = $DataRoot
& $condaExe run -n AiJava --no-capture-output python (Join-Path $PSScriptRoot 'build-neo4j-import.py')
if ($LASTEXITCODE -ne 0) {
    throw "Neo4j 导入数据生成失败，退出码：$LASTEXITCODE"
}

Write-Host "导入文件已生成：$DataRoot\processed\graph"
