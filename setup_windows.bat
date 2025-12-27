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

REM Ask user where to install
set "INSTALL_PATH="
if "%~1"=="" (
    echo.
    echo Installation Options:
    echo 1. Use current directory: %SCRIPT_DIR%
    echo 2. Use default: C:\EmberEye
    echo 3. Enter custom path
    echo.
    set /p "CHOICE=Select option (1/2/3): "
    
    if "!CHOICE!"=="1" (
        set "INSTALL_PATH=%SCRIPT_DIR%"
        echo Using current directory: !INSTALL_PATH!
    ) else if "!CHOICE!"=="2" (
        set "INSTALL_PATH=C:\EmberEye"
        echo Using default directory: !INSTALL_PATH!
    ) else if "!CHOICE!"=="3" (
        set /p "INSTALL_PATH=Enter installation path: "
        echo Using custom path: !INSTALL_PATH!
    ) else (
        echo Invalid choice. Using default directory.
        set "INSTALL_PATH=C:\EmberEye"
    )
) else (
    set "INSTALL_PATH=%~1"
    echo Using provided installation path: !INSTALL_PATH!
)

echo.

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
