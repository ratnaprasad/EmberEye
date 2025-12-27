@echo off
REM ============================================================================
REM EmberEye v1.0.0-beta - Windows Setup Launcher
REM ============================================================================
REM This is a simple launcher that executes the PowerShell setup script
REM with proper permissions and error handling.
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║      EmberEye v1.0.0-beta - Automated Windows Setup           ║
echo ╚════════════════════════════════════════════════════════════════╝
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

REM Default installation path
set "INSTALL_PATH=C:\EmberEye"

REM Check for command line arguments
if "%~1"=="" (
    echo Installation Path: %INSTALL_PATH%
    echo.
) else (
    set "INSTALL_PATH=%~1"
    echo Custom Installation Path: %INSTALL_PATH%
    echo.
)

REM Execute PowerShell script
echo Launching setup script...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%SCRIPT_DIR%setup_windows.ps1' -InstallPath '%INSTALL_PATH%'"

if errorlevel 1 (
    echo.
    echo ❌ Setup failed. Check the log files for details.
    pause
    exit /b 1
) else (
    echo.
    echo ✅ Setup completed successfully!
    pause
    exit /b 0
)
