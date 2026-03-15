@echo off
REM EmberEye Field App - App-Only Startup
REM Starts only the Field application (no RTSP/MediaMTX/PFDS)

echo ============================================================
echo EmberEye Field Application - App-Only Startup
echo ============================================================
echo.

echo Checking for existing EmberEye Field instances...
echo   Closing existing app window...
taskkill /F /FI "WINDOWTITLE eq EmberEye Field*" /T >nul 2>&1

echo   Stopping packaged executables if running...
taskkill /F /IM EmberEye-Field.exe /T >nul 2>&1
taskkill /F /IM EmberEye-Field-OneFile.exe /T >nul 2>&1

echo   Stopping Python script processes if running...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.CommandLine -and ($_.CommandLine -match 'embereye-field\\main.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

timeout /t 2 /nobreak >nul

echo [1/1] Starting EmberEye Field Application...
if "%EMBEREYE_FORCE_CPU%"=="1" (
	echo   Launching field app using active imported model - CPU-only mode...
	start "EmberEye Field" cmd /k "cd /d %~dp0 && set EMBEREYE_FIELD=1 && set EMBEREYE_FORCE_CPU=1 && set CUDA_VISIBLE_DEVICES=-1 && .venv\Scripts\python.exe embereye-field\main.py"
) else (
	echo   Launching field app using active imported model - GPU auto-detect mode...
	start "EmberEye Field" cmd /k "cd /d %~dp0 && set EMBEREYE_FIELD=1 && set EMBEREYE_FORCE_CPU=0 && .venv\Scripts\python.exe embereye-field\main.py"
)

echo.
echo ============================================================
echo Field app started successfully!
echo ============================================================
echo.
echo Field App:   Running in separate window
echo.
echo To stop the app, run: stop_field.bat
echo.
pause
