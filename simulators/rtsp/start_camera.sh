#!/bin/bash
# RTSP Camera Simulator - Linux/macOS Launcher
# Starts MediaMTX server and streams IMG_1318.MOV

echo "============================================================"
echo "RTSP Camera Simulator - Full Stack Startup"
echo "============================================================"
echo

# Trap to cleanup on exit
cleanup() {
    echo
    echo "Stopping MediaMTX server..."
    pkill -f mediamtx
    echo "Done!"
    exit 0
}

trap cleanup INT TERM

echo "[1/3] Starting MediaMTX RTSP Server..."
cd "$(dirname "$0")/mediamtx"
./mediamtx > /dev/null 2>&1 &
MEDIAMTX_PID=$!
cd ..
echo "  MediaMTX started (PID: $MEDIAMTX_PID)"
echo "  Waiting 3 seconds for server initialization..."
sleep 3
echo "  MediaMTX ready!"
echo

echo "[2/3] Starting Camera Simulator..."
echo "  Video: data/IMG_1318.MOV"
echo "  Stream URL: rtsp://localhost:8554/camera1"
echo

echo "[3/3] Launching FFmpeg streamer..."
python3 rtsp_camera_simulator.py --video data/IMG_1318.MOV --port 8554 --name camera1

# Cleanup on exit
cleanup
