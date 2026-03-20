@echo off
REM EmberEye Studio - Stop Script
REM Stops EmberEye Studio processes started via EXE or Python

setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

echo ============================================================
echo EmberEye Studio - Stop
echo ============================================================
echo.

echo Stopping EmberEye Studio executable processes...
taskkill /F /IM EmberEyeStudio.exe /T >nul 2>&1

echo Stopping Python-based Studio processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.CommandLine -and ($_.CommandLine -match 'embereye-studio\\main.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo Done. EmberEye Studio processes stopped (if any were running).
echo.
