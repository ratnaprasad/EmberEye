"""Compatibility shim: run embereye_base.app.calibrationcapture as script when executed."""
import runpy

if __name__ == "__main__":
    runpy.run_module("embereye_base.app.calibrationcapture", run_name="__main__")
else:
    from embereye_base.app.calibrationcapture import *  # noqa
