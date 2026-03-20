#!/usr/bin/env python3
"""Compatibility wrapper for scripts/build/build_msi.py"""
import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).with_name("scripts") / "build" / "build_msi.py"
    runpy.run_path(str(target), run_name="__main__")
