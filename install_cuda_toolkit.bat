@echo off
REM ============================================================================
REM NVIDIA CUDA Toolkit Installation Guide
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ================================================================
echo       NVIDIA CUDA Toolkit 12.8 - Installation Required
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
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%SCRIPT_DIR%install_cuda_toolkit.ps1'"

pause
