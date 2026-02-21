@echo off
REM EmberEye Studio - Startup Script
REM Launches EmberEye Studio using the project virtual environment when available

setlocal
cd /d "%~dp0"

echo ============================================================
echo EmberEye Studio - Startup
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    echo Using virtual environment Python...
    start "EmberEye Studio" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe embereye-studio\main.py"
) else (
    echo Virtual environment not found, using system Python...
    start "EmberEye Studio" cmd /k "cd /d %~dp0 && python embereye-studio\main.py"
)

echo Studio launch command sent.
echo.
