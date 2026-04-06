@echo off
REM EmberEye Studio - Startup Script
REM Launches EmberEye Studio using the project virtual environment when available

setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

echo ============================================================
echo EmberEye Studio - Startup
echo ============================================================
echo.

echo Configuring runtime for GPU auto-detection...
set "EMBEREYE_FORCE_CPU=0"
set "CUDA_VISIBLE_DEVICES=0"
set "EMBEREYE_DEVICE=auto"

if exist ".venv\Scripts\python.exe" (
    echo Using virtual environment Python...
    start "EmberEye Studio" cmd /k "cd /d %ROOT_DIR% && set EMBEREYE_FORCE_CPU=0&& set CUDA_VISIBLE_DEVICES=0&& set EMBEREYE_DEVICE=auto&& .venv\Scripts\python.exe embereye-studio\main.py"
) else (
    echo Virtual environment not found, using system Python...
    start "EmberEye Studio" cmd /k "cd /d %ROOT_DIR% && set EMBEREYE_FORCE_CPU=0&& set CUDA_VISIBLE_DEVICES=0&& set EMBEREYE_DEVICE=auto&& python embereye-studio\main.py"
)

echo Studio launch command sent.
echo.
