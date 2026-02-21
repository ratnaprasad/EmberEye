@echo off
REM ============================================================================
REM EmberEye - PyTorch Nightly Installation Launcher
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ================================================================
echo       EmberEye - PyTorch Nightly Installation
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
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%SCRIPT_DIR%install_pytorch_nightly.ps1'"

if errorlevel 1 (
    echo.
    echo Installation failed or was cancelled.
    pause
    exit /b 1
) else (
    echo.
    pause
    exit /b 0
)
