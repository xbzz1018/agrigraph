@echo off
setlocal EnableExtensions
if not defined PNPM_CMD set "PNPM_CMD=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
if not exist "%PNPM_CMD%" set "PNPM_CMD=pnpm.cmd"
cd /d "%~dp0..\..\frontend"
if not exist "%~dp0..\..\logs" mkdir "%~dp0..\..\logs"
call "%PNPM_CMD%" dev -- --host 127.0.0.1 --port 9627 > "%~dp0..\..\logs\frontend-dev.log" 2>&1
exit /b %ERRORLEVEL%
