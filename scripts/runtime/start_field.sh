#!/usr/bin/env bash
# EmberEye Field - Full Stack Startup (Linux/macOS)
# Starts RTSP simulator, Field app, and PFDS simulator

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

echo "============================================================"
echo "EmberEye Field Application - Full Stack Startup"
echo "============================================================"
echo

FIELD_FOREGROUND="${EMBEREYE_FIELD_FOREGROUND:-0}"

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON_BIN=".venv/Scripts/python.exe"
fi

echo "Checking for existing EmberEye Field stack processes..."
pkill -f "embereye-field/main.py" 2>/dev/null || true
pkill -f "simulators/rtsp/rtsp_camera_simulator.py" 2>/dev/null || true
pkill -f "simulators/pfds/pfds_simulator.py" 2>/dev/null || true
pkill -f "mediamtx" 2>/dev/null || true
sleep 1

echo "[1/4] Starting RTSP Camera Simulator..."
RTSP_ENABLED=1
RTSP_DISABLED_REASON=""
MEDIAMTX_SOURCE=""
MEDIAMTX_LOCAL_BIN="simulators/rtsp/mediamtx/mediamtx"
RTSP_VIDEO_FILE="${EMBEREYE_RTSP_VIDEO:-simulators/rtsp/data/IMG_0620.MOV}"

if [ ! -f "$RTSP_VIDEO_FILE" ] && [ -z "${EMBEREYE_RTSP_VIDEO:-}" ]; then
  if [ -d "simulators/rtsp/data" ]; then
    AUTO_VIDEO_FILE="$(find simulators/rtsp/data -maxdepth 1 -type f \( -iname '*.mov' -o -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.avi' -o -iname '*.webm' \) | head -n 1 || true)"
    if [ -n "$AUTO_VIDEO_FILE" ] && [ -f "$AUTO_VIDEO_FILE" ]; then
      RTSP_VIDEO_FILE="$AUTO_VIDEO_FILE"
      echo "  Auto-selected RTSP video: $RTSP_VIDEO_FILE"
    fi
  fi
fi

if [ ! -f "$RTSP_VIDEO_FILE" ]; then
  RTSP_ENABLED=0
  RTSP_DISABLED_REASON="missing video"
  echo "  Warning: RTSP video not found at $RTSP_VIDEO_FILE"
  echo "  Set EMBEREYE_RTSP_VIDEO to a valid file to enable RTSP."
fi

if [ "$RTSP_ENABLED" = "1" ] && [ -x "$MEDIAMTX_LOCAL_BIN" ]; then
  MEDIAMTX_SOURCE="local"
  (cd "simulators/rtsp/mediamtx" && ./mediamtx >/dev/null 2>&1 &)
  echo "  MediaMTX started (local binary)"
elif [ "$RTSP_ENABLED" = "1" ] && command -v mediamtx >/dev/null 2>&1; then
  MEDIAMTX_SOURCE="system-mediamtx"
  mediamtx >/dev/null 2>&1 &
  echo "  MediaMTX started (system 'mediamtx')"
elif [ "$RTSP_ENABLED" = "1" ] && command -v rtsp-simple-server >/dev/null 2>&1; then
  MEDIAMTX_SOURCE="system-rtsp-simple-server"
  rtsp-simple-server >/dev/null 2>&1 &
  echo "  MediaMTX-compatible server started (system 'rtsp-simple-server')"
elif [ "$RTSP_ENABLED" = "1" ]; then
  RTSP_ENABLED=0
  RTSP_DISABLED_REASON="missing MediaMTX"
  echo "  Warning: No usable MediaMTX binary found."
  echo "  Tip: install with 'brew install mediamtx'"
  echo "  RTSP + PFDS startup will be skipped."
fi

if [ "$RTSP_ENABLED" = "1" ]; then
  sleep 3

  "$PYTHON_BIN" simulators/rtsp/rtsp_camera_simulator.py \
    --video "$RTSP_VIDEO_FILE" \
    --port 8554 \
    --name camera1 >/dev/null 2>&1 &

  echo "  RTSP stream startup triggered"
  sleep 2

  echo "[2/4] Waiting for stream initialization..."
  sleep 2
  echo "  Stream stable"
else
  echo "[2/4] RTSP initialization skipped"
fi
echo

echo "[3/4] Starting EmberEye Field Application..."
if [ "$FIELD_FOREGROUND" = "1" ]; then
  if [ "${EMBEREYE_FORCE_CPU:-0}" = "1" ]; then
    echo "  Launching field app in CPU-only mode (foreground)"
  else
    echo "  Launching field app in GPU auto-detect mode (foreground)"
  fi
else
  if [ "${EMBEREYE_FORCE_CPU:-0}" = "1" ]; then
    echo "  Launching field app in CPU-only mode"
    EMBEREYE_FIELD=1 EMBEREYE_FORCE_CPU=1 CUDA_VISIBLE_DEVICES=-1 "$PYTHON_BIN" embereye-field/main.py >/dev/null 2>&1 &
  else
    echo "  Launching field app in GPU auto-detect mode"
    EMBEREYE_FIELD=1 EMBEREYE_FORCE_CPU=0 "$PYTHON_BIN" embereye-field/main.py >/dev/null 2>&1 &
  fi
fi

echo

PFDS_DATA_FILE="simulators/pfds/data/NEW DATA 10 MINS.txt"

if [ "$RTSP_ENABLED" = "1" ] && [ -f "$PFDS_DATA_FILE" ]; then
  echo "[4/4] Starting PFDS Simulator..."
  sleep 6
  "$PYTHON_BIN" simulators/pfds/pfds_simulator.py --host 127.0.0.1 --port 4888 --loc-id demo_room >/dev/null 2>&1 &
elif [ "$RTSP_ENABLED" = "1" ]; then
  echo "[4/4] PFDS Simulator skipped (missing data file: $PFDS_DATA_FILE)"
else
  echo "[4/4] PFDS Simulator skipped (RTSP disabled)"
fi

echo
echo "============================================================"
if [ "$FIELD_FOREGROUND" = "1" ]; then
  echo "Services started (UI in foreground mode)"
else
  echo "All services started (background mode)"
fi
echo "============================================================"
if [ "$RTSP_ENABLED" = "1" ]; then
  echo "RTSP Stream: rtsp://localhost:8554/camera1"
  if [ -f "$PFDS_DATA_FILE" ]; then
    echo "PFDS Sim:    127.0.0.1:4888 (demo_room)"
  else
    echo "PFDS Sim:    skipped (missing replay data)"
  fi
else
  if [ "$RTSP_DISABLED_REASON" = "missing video" ]; then
    echo "RTSP Stream: skipped (missing video file)"
  elif [ "$RTSP_DISABLED_REASON" = "missing MediaMTX" ]; then
    echo "RTSP Stream: skipped (no MediaMTX found)"
  else
    echo "RTSP Stream: skipped"
  fi
  echo "PFDS Sim:    skipped"
fi
echo "Field App:   embereye-field/main.py"
echo "Stop stack:  ./scripts/runtime/stop_field.sh"
echo

if [ "$FIELD_FOREGROUND" = "1" ]; then
  if [ "${EMBEREYE_FORCE_CPU:-0}" = "1" ]; then
    EMBEREYE_FIELD=1 EMBEREYE_FORCE_CPU=1 CUDA_VISIBLE_DEVICES=-1 "$PYTHON_BIN" embereye-field/main.py
  else
    EMBEREYE_FIELD=1 EMBEREYE_FORCE_CPU=0 "$PYTHON_BIN" embereye-field/main.py
  fi
fi