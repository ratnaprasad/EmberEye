#!/usr/bin/env python3
"""Compatibility wrapper for scripts/build/build_field_onefile.py"""
import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).with_name("scripts") / "build" / "build_field_onefile.py"
    runpy.run_path(str(target), run_name="__main__")
