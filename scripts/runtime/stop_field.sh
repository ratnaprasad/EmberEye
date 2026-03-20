#!/usr/bin/env bash
# EmberEye Field - Stop Script (Linux/macOS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

echo "============================================================"
echo "Stopping EmberEye Field Application Stack"
echo "============================================================"
echo

echo "Stopping EmberEye Field application..."
pkill -f "embereye-field/main.py" 2>/dev/null || true
pkill -f "EmberEye-Field" 2>/dev/null || true

echo "Stopping RTSP camera simulator..."
pkill -f "rtsp_camera_simulator.py" 2>/dev/null || true
pkill -f ffmpeg 2>/dev/null || true

echo "Stopping PFDS simulator..."
pkill -f "pfds_simulator.py" 2>/dev/null || true

echo "Stopping MediaMTX server..."
pkill -f mediamtx 2>/dev/null || true

echo
echo "All EmberEye Field stack services stopped (if running)."
echo