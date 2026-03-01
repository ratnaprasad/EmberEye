@echo off
REM EmberEye Field App - Full Stack Startup
REM Starts RTSP simulator and Field application together

echo ============================================================
echo EmberEye Field Application - Full Stack Startup
echo ============================================================
echo.

echo Checking for existing EmberEye Field instances...
echo   Closing existing app/simulator windows...
taskkill /F /FI "WINDOWTITLE eq EmberEye Field*" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq RTSP Camera*" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq PFDS Simulator*" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq MediaMTX Server*" /T >nul 2>&1

echo   Stopping packaged executables if running...
taskkill /F /IM EmberEye-Field.exe /T >nul 2>&1
taskkill /F /IM EmberEye-Field-OneFile.exe /T >nul 2>&1
taskkill /F /IM mediamtx.exe /T >nul 2>&1

echo   Stopping Python script processes if running...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.CommandLine -and ($_.CommandLine -match 'embereye-field\\main.py' -or $_.CommandLine -match 'simulators\\rtsp\\rtsp_camera_simulator.py' -or $_.CommandLine -match 'simulators\\pfds\\pfds_simulator.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

timeout /t 2 /nobreak >nul

echo [1/4] Starting RTSP Camera Simulator...
echo   Starting MediaMTX server...
start "MediaMTX Server" /D "%~dp0simulators\rtsp\mediamtx" mediamtx.exe
timeout /t 3 /nobreak >nul

echo   Starting camera stream (IMG_0620.MOV)...
start "RTSP Camera" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe simulators\rtsp\rtsp_camera_simulator.py --video simulators\rtsp\data\IMG_0620.MOV --port 8554 --name camera1"
timeout /t 3 /nobreak >nul

echo   RTSP Stream ready at: rtsp://localhost:8554/camera1
echo.

echo [2/4] Waiting for stream initialization...
timeout /t 2 /nobreak >nul
echo   Stream stable!
echo.

echo [3/4] Starting EmberEye Field Application...
if "%EMBEREYE_FORCE_CPU%"=="1" (
	echo   Launching field app using active imported model - CPU-only mode...
	start "EmberEye Field" cmd /k "cd /d %~dp0 && set EMBEREYE_FORCE_CPU=1 && set CUDA_VISIBLE_DEVICES=-1 && .venv\Scripts\python.exe embereye-field\main.py"
) else (
	echo   Launching field app using active imported model - GPU auto-detect mode...
	start "EmberEye Field" cmd /k "cd /d %~dp0 && set EMBEREYE_FORCE_CPU=0 && .venv\Scripts\python.exe embereye-field\main.py"
)

echo.
echo [4/4] Starting PFDS Simulator...
echo   Waiting for Field TCP server initialization...
timeout /t 6 /nobreak >nul
start "PFDS Simulator" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe simulators\pfds\pfds_simulator.py --host 127.0.0.1 --port 4888 --loc-id demo_room"

echo.
echo ============================================================
echo All services started successfully!
echo ============================================================
echo.
echo RTSP Stream: rtsp://localhost:8554/camera1
echo PFDS Sim:    127.0.0.1:4888 (demo_room)
echo Field App:   Running in separate window
echo.
echo To stop all services, run: stop_field.bat
echo.
pause
