#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper for stable suite builds on release/1.1
# Usage:
#   ./build_suite.sh
#   ./build_suite.sh --field-mode onefile --clean

exec python scripts/build_suite_1x.py --field-mode onedir --clean "$@"
