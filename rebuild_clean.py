#!/usr/bin/env python
import shutil
import sys
import os

os.chdir("D:\\EE\\EmberEye-develop-2.x")
print("[CLEANUP] Removing dist/build...")
shutil.rmtree("dist", ignore_errors=True)
shutil.rmtree("build", ignore_errors=True)
shutil.rmtree(".pyinstaller", ignore_errors=True)
print("[CLEANUP] Removed old builds successfully")

# Now run PyInstaller with clean flag
print("[BUILD] Starting PyInstaller clean rebuild...")
os.system(f'"{sys.executable}" -m PyInstaller --noconfirm --clean EmberEye_Field_OneDir.spec')
print("[BUILD] PyInstaller complete")
