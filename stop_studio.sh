#!/usr/bin/env bash
# EmberEye Studio - Stop Script
# Stops EmberEye Studio processes started via EXE or Python

set -e

echo "============================================================"
echo "EmberEye Studio - Stop"
echo "============================================================"
echo

echo "Stopping EmberEyeStudio.exe (if running)..."
pkill -f "EmberEyeStudio.exe" 2>/dev/null || true

echo "Stopping Python studio main process (if running)..."
pkill -f "embereye-studio/main.py" 2>/dev/null || true

echo "Done. EmberEye Studio processes stopped (if any were running)."
echo
