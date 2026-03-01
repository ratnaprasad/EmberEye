#!/usr/bin/env bash
# EmberEye Studio - Startup Script
# Launches EmberEye Studio using the project virtual environment when available

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "EmberEye Studio - Startup"
echo "============================================================"
echo

if [ -x ".venv/bin/python" ]; then
  echo "Using virtual environment Python..."
  exec .venv/bin/python embereye-studio/main.py
elif [ -x ".venv/Scripts/python.exe" ]; then
  echo "Using virtual environment Python (Windows venv layout)..."
  exec .venv/Scripts/python.exe embereye-studio/main.py
else
  echo "Virtual environment not found, using system Python..."
  exec python embereye-studio/main.py
fi
