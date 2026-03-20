"""Compatibility shim: run embereye_base.app.CalibrationWindow as script when executed."""
import runpy

if __name__ == "__main__":
    runpy.run_module("embereye_base.app.CalibrationWindow", run_name="__main__")
else:
    from embereye_base.app.CalibrationWindow import *  # noqa
