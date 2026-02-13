#!/bin/bash
# Stop RTSP Camera Simulator and MediaMTX Server

echo "============================================================"
echo "Stopping RTSP Camera Simulator"
echo "============================================================"
echo

echo "Stopping FFmpeg processes..."
pkill -f ffmpeg && echo "  FFmpeg stopped" || echo "  No FFmpeg processes found"

echo "Stopping Python simulator processes..."
pkill -f rtsp_camera_simulator && echo "  Simulator stopped" || echo "  No simulator processes found"

echo "Stopping MediaMTX server..."
pkill -f mediamtx && echo "  MediaMTX stopped" || echo "  No MediaMTX processes found"

echo
echo "All services stopped!"
