#!/usr/bin/env python
"""
Build EmberEye Studio.exe installer using PyInstaller
"""
import os
import sys
import subprocess
from pathlib import Path

def build_installer():
    """Build the installer using PyInstaller"""
    
    print("=" * 60)
    print("EmberEye Studio - Building Installer")
    print("=" * 60)
    
    # Get studio directory
    studio_dir = Path(__file__).parent
    dist_dir = studio_dir / "dist"
    
    print(f"\n[1/5] Studio Directory: {studio_dir}")
    print(f"[2/5] Output Directory: {dist_dir}")
    
    # PyInstaller command
    pyinstaller_cmd = [
        "pyinstaller",
        "--name", "EmberEyeStudio",
        "--onefile",  # Single executable file
        "--windowed",  # No console window
        "--icon", str(studio_dir / "icon.ico") if (studio_dir / "icon.ico").exists() else None,
        "--add-data", f"{studio_dir}:.",
        "--hidden-import=PyQt5",
        "--hidden-import=torch",
        "--hidden-import=cv2",
        "--hidden-import=ultralytics",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--collect-all=ultralytics",
        "--collect-all=PyQt5",
        str(studio_dir / "main.py")
    ]
    
    # Remove None values (icon if not exists)
    pyinstaller_cmd = [cmd for cmd in pyinstaller_cmd if cmd is not None]
    
    print(f"\n[3/5] Running PyInstaller...")
    print(f"Command: {' '.join(pyinstaller_cmd[:5])} ...")
    
    try:
        result = subprocess.run(pyinstaller_cmd, cwd=str(studio_dir), capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"[4/5] ✓ Build completed successfully!")
            
            exe_file = dist_dir / "EmberEyeStudio.exe"
            if exe_file.exists():
                file_size = exe_file.stat().st_size / (1024*1024)
                print(f"\n[5/5] ✓ Executable created: {exe_file}")
                print(f"      File size: {file_size:.2f} MB")
                print("\n" + "=" * 60)
                print("Build Complete!")
                print("=" * 60)
                print(f"\nExecutable location:")
                print(f"  {exe_file}")
                print(f"\nTo run: Double-click EmberEyeStudio.exe or run:")
                print(f"  {exe_file}")
                return True
            else:
                print(f"✗ Executable not found at {exe_file}")
                return False
        else:
            print(f"✗ Build failed!")
            print(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ Error building installer: {e}")
        return False

if __name__ == "__main__":
    success = build_installer()
    sys.exit(0 if success else 1)
