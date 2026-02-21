@echo off
REM Stop EmberEye Field App and RTSP Simulator

echo ============================================================
echo Stopping EmberEye Field Application Stack
echo ============================================================
echo.

echo Stopping EmberEye Field Application...
taskkill /F /FI "WINDOWTITLE eq EmberEye Field*" /T >nul 2>&1
taskkill /F /IM EmberEye-Field.exe /T >nul 2>&1
taskkill /F /IM EmberEye-Field-OneFile.exe /T >nul 2>&1

echo Stopping RTSP Camera Simulator...
taskkill /F /IM ffmpeg.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq RTSP Camera*" /T >nul 2>&1

echo Stopping PFDS Simulator...
taskkill /F /FI "WINDOWTITLE eq PFDS Simulator*" /T >nul 2>&1

echo Stopping MediaMTX Server...
taskkill /F /IM mediamtx.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq MediaMTX Server*" /T >nul 2>&1

echo Stopping Python script processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.CommandLine -and ($_.CommandLine -match 'embereye-field\\main.py' -or $_.CommandLine -match 'simulators\\rtsp\\rtsp_camera_simulator.py' -or $_.CommandLine -match 'simulators\\pfds\\pfds_simulator.py') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo ============================================================
echo All services stopped!
echo ============================================================
echo.
pause
