"""Compatibility shim: run embereye_base.core.thermal.calibrate_thermal as script when executed."""
import runpy

if __name__ == "__main__":
    runpy.run_module("embereye_base.core.thermal.calibrate_thermal", run_name="__main__")
else:
    from embereye_base.core.thermal.calibrate_thermal import *  # noqa
