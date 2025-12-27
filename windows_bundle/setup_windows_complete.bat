@echo off
setlocal ENABLEDELAYEDEXPANSION

REM EmberEye Windows setup & build script (ZIP-based)
REM Usage: Double-click or run in cmd: setup_windows_complete.bat

REM Detect script directory (bundle root)
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
cd /d "%PROJECT_ROOT%"

REM Prerequisites check
where python >nul 2>nul || (
  echo [ERROR] Python not found in PATH. Install Python 3.11 and retry.
  exit /b 1
)

REM Optional: check pyinstaller
python -c "import PyInstaller" >nul 2>nul || (
  echo [INFO] PyInstaller not found. Will install in venv.
)

REM Create venv
if not exist .venv (
  echo [INFO] Creating virtual environment...
  python -m venv .venv || (
    echo [ERROR] Failed to create venv.
    exit /b 1
  )
)

REM Activate venv
call .venv\Scripts\activate || (
  echo [ERROR] Failed to activate venv.
  exit /b 1
)

REM Upgrade pip
python -m pip install --upgrade pip setuptools wheel

REM Install dependencies
if exist requirements.txt (
  echo [INFO] Installing requirements...
  python -m pip install -r requirements.txt || (
    echo [ERROR] Failed to install requirements.
    exit /b 1
  )
) else (
  echo [WARN] requirements.txt not found; continuing.
)

REM Ensure PyInstaller
python -m pip install pyinstaller || (
  echo [ERROR] Failed to install PyInstaller.
  exit /b 1
)

REM Prepare runtime files
if not exist logs (
  mkdir logs
)
if not exist ip_loc_map.db (
  if exist ip_loc_map.json (
    echo {}>ip_loc_map.json
  ) else (
    echo {}>ip_loc_map.json
  )
)
if not exist stream_config.json (
  echo {"groups":["Default"],"streams":[],"tcp_port":9001}>stream_config.json
)

REM Clean previous build
if exist build (
  rmdir /s /q build
)
if exist dist (
  rmdir /s /q dist
)

REM Build EXE with PyInstaller spec
if exist EmberEye.spec (
  echo [INFO] Building with EmberEye.spec...
  pyinstaller EmberEye.spec || (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
  )
) else (
  echo [INFO] Spec not found; building onefile from main.py...
  pyinstaller -y --noconfirm --clean --windowed --name EmberEye ^
    --add-data "logo.png;." ^
    --add-data "images;images" ^
    --add-data "stream_config.json;." ^
    --add-data "ip_loc_map.db;." ^
    --add-data "ip_loc_map.json;." ^
    --add-data "logs;logs" ^
    main.py || (
    echo [ERROR] Fallback build failed.
    exit /b 1
  )
)

REM Done
echo [SUCCESS] Build complete. EXE located in dist\EmberEye\ or dist\EmberEye.exe.
endlocal