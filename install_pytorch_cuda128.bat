@echo off
REM ============================================================================
REM EmberEye - PyTorch CUDA 12.8+ Installation Launcher
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ================================================================
echo       EmberEye - PyTorch CUDA 12.8+ Installation
echo ================================================================
echo.

REM Check if PowerShell is available
where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell not found
    pause
    exit /b 1
)

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"

REM Execute PowerShell script
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%SCRIPT_DIR%install_pytorch_cuda128.ps1'"

if errorlevel 1 (
    echo.
    echo Installation failed or not yet available.
    pause
    exit /b 1
) else (
    echo.
    pause
    exit /b 0
)
