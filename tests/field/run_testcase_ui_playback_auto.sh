#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

DELAY_SET=0
for arg in "$@"; do
  if [[ "$arg" == "--delay" ]]; then
    DELAY_SET=1
    break
  fi
done

if [[ $DELAY_SET -eq 1 ]]; then
  exec python tests/field/run_testcase_ui_playback.py --auto "$@"
else
  exec python tests/field/run_testcase_ui_playback.py --auto --delay "${DELAY:-5}" "$@"
fi
