@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d %~dp0

set "PYTHON_PORT=8188"
set "FRONTEND_PORT=9627"
set "CONDA_EXE="
set "ACCEPTANCE_ENV=%~dp0var\acceptance\infra.env"
set "PNPM_CMD=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
if not exist "%PNPM_CMD%" set "PNPM_CMD=pnpm"

if defined AGRIGRAPH_CONDA_EXE if exist "%AGRIGRAPH_CONDA_EXE%" set "CONDA_EXE=%AGRIGRAPH_CONDA_EXE%"
if not defined CONDA_EXE for /f "delims=" %%I in ('where conda.exe 2^>nul') do if not defined CONDA_EXE set "CONDA_EXE=%%I"
if not defined CONDA_EXE (
  echo [ERROR] Conda was not found. Add it to PATH or set AGRIGRAPH_CONDA_EXE.
  exit /b 1
)
for %%I in ("%CONDA_EXE%") do if /I not "%%~xI"==".exe" (
  echo [ERROR] AGRIGRAPH_CONDA_EXE must point to conda.exe, not a batch wrapper: %CONDA_EXE%
  exit /b 1
)
set "AGRIGRAPH_CONDA_EXE=%CONDA_EXE%"

if exist ".env.ai" for /f "usebackq tokens=1,* delims==" %%A in (".env.ai") do (
  if /I "%%A"=="AGRIGRAPH_PORT" set "PYTHON_PORT=%%B"
)
if exist "frontend\.env.test" for /f "usebackq tokens=1,* delims==" %%A in ("frontend\.env.test") do (
  if /I "%%A"=="VITE_PORT" set "FRONTEND_PORT=%%B"
)
if not exist "logs" mkdir "logs"

echo ====================================
echo Start AgriGraph Evidence QA
echo ====================================

echo [1/3] Checking AiJava...
"%CONDA_EXE%" run -n AiJava python -c "import os,sys; assert os.path.basename(sys.prefix).lower() == 'aijava', sys.prefix; print(sys.executable); print(sys.version); print('Conda env: AiJava')"
if errorlevel 1 exit /b 1

echo [2/3] Starting Python main backend on %PYTHON_PORT%...
start "AgriGraph Evidence QA Backend" /min powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\dev\run-python-backend-aijava.ps1" -Port %PYTHON_PORT% -EnvFilePath "%ACCEPTANCE_ENV%" ^> "%~dp0logs\python-backend.log" 2^>^&1
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:%PYTHON_PORT%/api/v1/health';if($r.StatusCode -eq 200){exit 0}}catch{};Start-Sleep -Seconds 1};exit 1"
if errorlevel 1 (
  echo [WARN] Python backend health check timed out. See logs\python-backend.log
) else (
  echo [OK] Python backend is healthy.
)

echo [3/3] Starting frontend on %FRONTEND_PORT%...
start "AgriGraph Frontend" /min "%~dp0scripts\dev\run-frontend.cmd"

echo.
echo Python API: http://127.0.0.1:%PYTHON_PORT%/api/v1/health
echo Agent UI:  http://127.0.0.1:%FRONTEND_PORT%
echo Stop:      stop-windows.bat
echo ====================================
