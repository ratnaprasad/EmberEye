import os
import ctypes
from pathlib import Path

ROOT = Path("D:/EE/EmberEye-develop-2.x")
venv_torch_lib = ROOT / ".venv/Lib/site-packages/torch/lib"
dist_torch_lib = ROOT / "dist/EmberEye-Field-GPU/_internal/torch/lib"
dist_internal = ROOT / "dist/EmberEye-Field-GPU/_internal"

print("=== Compare venv torch/lib vs dist torch/lib ===")
venv = sorted([p.name for p in venv_torch_lib.glob("*.dll")])
dist = sorted([p.name for p in dist_torch_lib.glob("*.dll")])
print("venv count:", len(venv))
print("dist count:", len(dist))
missing_in_dist = [x for x in venv if x not in dist]
extra_in_dist = [x for x in dist if x not in venv]
print("missing_in_dist:", missing_in_dist)
print("extra_in_dist:", extra_in_dist)

print("\n=== Manual c10.dll load test (dist) ===")
for p in [dist_internal, dist_torch_lib]:
    if p.exists():
        os.add_dll_directory(str(p))
        print("add_dll_directory:", p)

for dll in ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "ucrtbase.dll", "dbghelp.dll"]:
    try:
        ctypes.CDLL(dll)
        print("OK", dll)
    except OSError as e:
        print("FAIL", dll, e)

c10 = dist_torch_lib / "c10.dll"
print("c10 path exists:", c10.exists(), c10)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.LoadLibraryExW.restype = ctypes.c_void_p
h = k32.LoadLibraryExW(str(c10), None, 0x00001100)
if h:
    print("LoadLibraryExW c10: OK")
else:
    err = ctypes.get_last_error()
    print("LoadLibraryExW c10: FAIL", err)
    try:
        raise ctypes.WinError(err)
    except OSError as e:
        print("WinError detail:", e)

print("\n=== Try loading torch_global_deps then c10 ===")
for dep in ["torch_global_deps.dll", "torch_cpu.dll", "torch.dll"]:
    p = dist_torch_lib / dep
    if p.exists():
        try:
            ctypes.CDLL(str(p))
            print("OK", dep)
        except OSError as e:
            print("FAIL", dep, e)

h2 = k32.LoadLibraryExW(str(c10), None, 0x00001100)
if h2:
    print("LoadLibraryExW c10 after deps: OK")
else:
    err2 = ctypes.get_last_error()
    print("LoadLibraryExW c10 after deps: FAIL", err2)
    try:
        raise ctypes.WinError(err2)
    except OSError as e:
        print("WinError detail after deps:", e)
