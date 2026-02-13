@echo off
REM Stop RTSP Camera Simulator and MediaMTX Server

echo ============================================================
echo Stopping RTSP Camera Simulator
echo ============================================================
echo.

echo Stopping FFmpeg processes...
taskkill /F /IM ffmpeg.exe >nul 2>&1
if %errorlevel% == 0 (
    echo   FFmpeg stopped
) else (
    echo   No FFmpeg processes found
)

echo Stopping Python simulator processes...
taskkill /F /FI "WINDOWTITLE eq *rtsp_camera*" >nul 2>&1

echo Stopping MediaMTX server...
taskkill /F /IM mediamtx.exe >nul 2>&1
if %errorlevel% == 0 (
    echo   MediaMTX stopped
) else (
    echo   No MediaMTX processes found
)

echo.
echo All services stopped!
echo.
pause
