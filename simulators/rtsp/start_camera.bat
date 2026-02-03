@echo off
REM RTSP Camera Simulator - Windows Launcher
REM Streams IMG_1318.MOV from data folder

echo Starting RTSP Camera Simulator...
echo.

python rtsp_camera_simulator.py --video ..\data\IMG_1318.MOV --port 8554 --name camera1

pause
