@echo off
REM RTSP Camera Simulator - Windows Launcher
REM Starts MediaMTX server and streams IMG_0620.MOV

echo ============================================================
echo RTSP Camera Simulator - Full Stack Startup
echo ============================================================
echo.

echo [1/3] Starting MediaMTX RTSP Server...
start "MediaMTX Server" /D "%~dp0mediamtx" mediamtx.exe
echo   MediaMTX starting in separate window...
echo   Waiting 3 seconds for server initialization...
timeout /t 3 /nobreak >nul
echo   MediaMTX ready!
echo.

echo [2/3] Starting Camera Simulator...
echo   Video: data\IMG_0620.MOV
echo   Stream URL: rtsp://localhost:8554/camera1
echo.

echo [3/3] Launching FFmpeg streamer...
python rtsp_camera_simulator.py --video data\IMG_0620.MOV --port 8554 --name camera1

echo.
echo ============================================================
echo Stream stopped. Press any key to close MediaMTX and exit...
echo ============================================================
pause >nul

echo Stopping MediaMTX server...
taskkill /F /IM mediamtx.exe >nul 2>&1

echo Done!
