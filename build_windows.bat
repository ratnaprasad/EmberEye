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

REM Use Windows-specific spec that excludes torch/ultralytics to avoid DLL init errors
if exist "EmberEye_win.spec" (
    echo [*] Using EmberEye_win.spec (excludes torch/ultralytics)
    pyinstaller --clean EmberEye_win.spec
) else (
    echo WARNING: EmberEye_win.spec not found, falling back to inline build
    set ICON_FLAG=
    if exist "logo.ico" (
        set ICON_FLAG=--icon logo.ico
    )
    pyinstaller --onefile ^
        --windowed ^
        --name "EmberEye" ^
        --paths . ^
        --paths embereye ^
        %ICON_FLAG% ^
        --collect-all=cv2 ^
        --distpath dist ^
        --workpath build ^
        --specpath . ^
        main.py
)

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
echo Executable: dist\EmberEye\EmberEye.exe
echo Build directory: dist\EmberEye\
echo.
echo Next steps:
echo 1. Test the executable: dist\EmberEye\EmberEye.exe
echo 2. Create ZIP package: Compress-Archive -Path dist/EmberEye/* -DestinationPath EmberEye_Windows.zip -Force
echo 3. Distribute EmberEye_Windows.zip to team
echo.
echo ========================================
echo.

pause
