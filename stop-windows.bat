@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d %~dp0

set "PYTHON_PORT=8188"
set "FRONTEND_PORT=9627"
if exist ".env.ai" for /f "usebackq tokens=1,* delims==" %%A in (".env.ai") do (
  if /I "%%A"=="AGRIGRAPH_PORT" set "PYTHON_PORT=%%B"
)

echo Stopping AgriGraph local services...
taskkill /FI "WINDOWTITLE eq AgriGraph Python Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AgriGraph Frontend*" /F >nul 2>&1
for %%P in (%PYTHON_PORT% %FRONTEND_PORT%) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do taskkill /PID %%I /F >nul 2>&1
)
echo Done.
