@echo off
setlocal

REM Usage:
REM   preflight_runtime_offline.bat
REM   preflight_runtime_offline.bat install "D:\path\to\runtime_bundle"

set MODE=%~1
set BUNDLE=%~2

if /I "%MODE%"=="install" (
    if "%BUNDLE%"=="" (
        echo [FAIL] Missing bundle path.
        echo Example: preflight_runtime_offline.bat install "D:\runtime_bundle"
        exit /b 1
    )
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preflight_runtime_offline.ps1" -Install -BundlePath "%BUNDLE%"
    exit /b %ERRORLEVEL%
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preflight_runtime_offline.ps1"
exit /b %ERRORLEVEL%
