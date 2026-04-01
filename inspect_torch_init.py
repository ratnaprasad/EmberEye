"""Check torch's Windows DLL loading logic."""
import sys
sys.path.insert(0, "D:/EE/EmberEye-develop-2.x/.venv/Lib/site-packages")

import inspect, torch._C
torch_init = "D:/EE/EmberEye-develop-2.x/.venv/Lib/site-packages/torch/__init__.py"

with open(torch_init, encoding="utf-8") as f:
    src = f.read()

# Find the DLL loading section
lines = src.split("\n")
for i, line in enumerate(lines):
    if any(kw in line for kw in ["add_dll_directory", "WinDLL", "_load_dll_libraries", "torchdir", "libiomp5md", "c10.dll", "LoadLibrary"]):
        print(f"{i+1:4d}: {line}")
