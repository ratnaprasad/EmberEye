@echo off
REM EmberEye Field App - Full Stack Startup
REM Starts RTSP simulator and Field application together

echo ============================================================
echo EmberEye Field Application - Full Stack Startup
echo ============================================================
echo.

echo [1/3] Starting RTSP Camera Simulator...
echo   Starting MediaMTX server...
start "MediaMTX Server" /D "%~dp0simulators\rtsp\mediamtx" mediamtx.exe
timeout /t 3 /nobreak >nul

echo   Starting camera stream (IMG_1318.MOV)...
start "RTSP Camera" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe simulators\rtsp\rtsp_camera_simulator.py --video simulators\rtsp\data\IMG_1318.MOV --port 8554 --name camera1"
timeout /t 3 /nobreak >nul

echo   RTSP Stream ready at: rtsp://localhost:8554/camera1
echo.

echo [2/3] Waiting for stream initialization...
timeout /t 2 /nobreak >nul
echo   Stream stable!
echo.

echo [3/3] Starting EmberEye Field Application...
echo   Launching field app...
start "EmberEye Field" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe embereye-field\main.py"

echo.
echo ============================================================
echo All services started successfully!
echo ============================================================
echo.
echo RTSP Stream: rtsp://localhost:8554/camera1
echo Field App:   Running in separate window
echo.
echo To stop all services, run: stop_field.bat
echo.
pause
