"""Diagnostic: inspect what DLLs exist in the packaged dist."""
import os
from pathlib import Path

dist = Path("D:/EE/EmberEye-develop-2.x/dist/EmberEye-Field-GPU/_internal")

print("=== ROOT _internal DLLs ===")
root_dlls = sorted(f.name for f in dist.glob("*.dll"))
for d in root_dlls:
    print(" ", d)

print("\n=== torch/lib DLLs ===")
torch_lib = dist / "torch" / "lib"
if torch_lib.exists():
    torch_dlls = sorted(f.name for f in torch_lib.glob("*.dll"))
    for d in torch_dlls:
        print(" ", d)
else:
    print("  NOT FOUND:", torch_lib)

print("\n=== vcruntime/msvcp in _internal root ===")
for name in ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll"]:
    p = dist / name
    print(f"  {name}: {'EXISTS' if p.exists() else 'MISSING'}")

print("\n=== c10.dll location ===")
for d in [dist, dist / "torch" / "lib"]:
    p = d / "c10.dll"
    print(f"  {p}: {'EXISTS' if p.exists() else 'MISSING'}")

print("\n=== c10.dll dependencies (pefile) ===")
try:
    import pefile
    c10 = dist / "torch" / "lib" / "c10.dll"
    if c10.exists():
        pe = pefile.PE(str(c10), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                dep = entry.dll.decode()
                # Check if it's in bundle or system
                in_root = (dist / dep).exists()
                in_torch = (dist / "torch" / "lib" / dep).exists()
                status = "IN_BUNDLE_ROOT" if in_root else ("IN_TORCH_LIB" if in_torch else "SYSTEM/MISSING")
                print(f"  {dep} -> {status}")
except ImportError:
    print("  pefile not installed, skipping")
except Exception as e:
    print(f"  Error: {e}")
