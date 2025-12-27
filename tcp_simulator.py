"""
Deprecated shim. The TCP simulator has moved to simulators/tcp_simulator.py.
This file forwards execution to the new location to avoid breaking workflows.
"""

from simulators.tcp_simulator import main  # type: ignore

if __name__ == "__main__":
    main()
