#!/usr/bin/env python3
"""Compatibility wrapper for scripts/build/create_windows_package.py"""
import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).with_name("scripts") / "build" / "create_windows_package.py"
    runpy.run_path(str(target), run_name="__main__")
