#!/bin/bash
# RTSP Camera Simulator - Linux/macOS Launcher
# Streams IMG_1318.MOV from data folder

echo "Starting RTSP Camera Simulator..."
echo

python3 rtsp_camera_simulator.py --video ../data/IMG_1318.MOV --port 8554 --name camera1
