@echo off
REM Stop EmberEye Field App and RTSP Simulator

echo ============================================================
echo Stopping EmberEye Field Application Stack
echo ============================================================
echo.

echo Stopping EmberEye Field Application...
taskkill /F /FI "WINDOWTITLE eq *EmberEye Field*" >nul 2>&1
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *embereye-field*" >nul 2>&1

echo Stopping RTSP Camera Simulator...
taskkill /F /IM ffmpeg.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *RTSP Camera*" >nul 2>&1

echo Stopping MediaMTX Server...
taskkill /F /IM mediamtx.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *MediaMTX*" >nul 2>&1

echo.
echo ============================================================
echo All services stopped!
echo ============================================================
echo.
pause
