"""
Deprecated shim. The TCP simulator now lives in tcp_sensor_simulator_v3.py.
This file forwards execution to the v3 simulator to avoid breaking workflows.
"""

import runpy
from pathlib import Path


if __name__ == "__main__":
    target = Path(__file__).with_name("tcp_sensor_simulator_v3.py")
    runpy.run_path(str(target), run_name="__main__")
