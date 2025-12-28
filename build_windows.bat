@echo off
REM EmberEye v1.0.0-beta - Windows Build Script
REM Generates .exe and installer for distribution

setlocal enabledelayedexpansion

echo.
echo ========================================
echo EmberEye v1.0.0-beta - Windows Builder
echo ========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.12+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    exit /b 1
)

REM Check Git installation
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git not found in PATH
    echo Please install Git from https://git-scm.com/download/win
    exit /b 1
)

echo [OK] Python and Git found

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo.
    echo [1/5] Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        exit /b 1
    )
)

REM Activate virtual environment
echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo [3/5] Installing dependencies...
pip install --upgrade pip setuptools wheel >nul 2>&1
pip install -r requirements.txt >nul 2>&1
pip install PyInstaller >nul 2>&1

if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)

REM Build executable
echo [4/5] Building executable (this may take 2-5 minutes)...

set ICON_FLAG=
if exist "logo.ico" (
    set ICON_FLAG=--icon logo.ico
)

REM Build PyInstaller command with conditional data directories
set DATA_FLAGS=
if exist "embereye\resources" (
    set DATA_FLAGS=!DATA_FLAGS! --add-data "embereye/resources;embereye/resources"
)
if exist "embereye\utils" (
    set DATA_FLAGS=!DATA_FLAGS! --add-data "embereye/utils;embereye/utils"
)
if exist "embereye\config" (
    set DATA_FLAGS=!DATA_FLAGS! --add-data "embereye/config;embereye/config"
)

pyinstaller --onefile ^
    --windowed ^
    --name "EmberEye" ^
    %ICON_FLAG% ^
    %DATA_FLAGS% ^
    --hidden-import=torch ^
    --hidden-import=torchvision ^
    --hidden-import=ultralytics ^
    --hidden-import=cv2 ^
    --hidden-import=PyQt5 ^
    --collect-all=ultralytics ^
    --collect-all=torch ^
    --collect-all=cv2 ^
    --distpath dist ^
    --workpath build ^
    --specpath . ^
    main.py

if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)

echo [5/5] Build complete!
echo.
echo ========================================
echo BUILD RESULTS
echo ========================================
echo.
echo Executable: dist\EmberEye.exe
echo Size: ~1GB (includes all dependencies)
echo.
echo Next steps:
echo 1. Test the executable: dist\EmberEye.exe
echo 2. Create installer (optional): run build_installer.bat
echo 3. Distribute to team
echo.
echo ========================================
echo.

pause
