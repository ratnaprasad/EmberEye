#!/usr/bin/env python
"""Build EmberEye Studio executable with PyInstaller.

Retired for 2.x direct usage. Use scripts/build_suite_2x.py instead.
Set EMBEREYE_ALLOW_LEGACY_BUILD=1 (or pass --allow-legacy) only for
compatibility workflows.
"""
import os
import sys
import subprocess
from pathlib import Path


def guard_legacy_usage() -> None:
    allow_flag = '--allow-legacy' in sys.argv
    if allow_flag:
        sys.argv.remove('--allow-legacy')
    if allow_flag or os.getenv('EMBEREYE_ALLOW_LEGACY_BUILD') == '1':
        return
    print('[RETIRED] embereye-studio/build_installer.py is retired for 2.x development.')
    print('[ACTION] Use: python scripts/build_suite_2x.py')
    print('[NOTE] For compatibility-only runs set EMBEREYE_ALLOW_LEGACY_BUILD=1 or pass --allow-legacy.')
    raise SystemExit(2)

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
    
    legacy_build_dir = studio_dir / "build"
    if legacy_build_dir.exists():
        import shutil
        shutil.rmtree(legacy_build_dir, ignore_errors=True)
    if dist_dir.exists():
        import shutil
        shutil.rmtree(dist_dir, ignore_errors=True)

    isolated_work_dir = studio_dir.parent / "build" / "studio_pyinstaller"
    isolated_work_dir.mkdir(parents=True, exist_ok=True)

    # Use the current Python environment so the suite build and direct runs are consistent.
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--name", "EmberEyeStudio",
        "--onedir",   # Directory bundle - avoids 5-min extraction delay for large apps
        "--windowed",  # No console window
        "--workpath", str(isolated_work_dir),
        "--specpath", str(isolated_work_dir),
        "--add-data", f"{studio_dir}{os.pathsep}.",
        "--hidden-import=PyQt6",
        "--hidden-import=torch",
        "--hidden-import=cv2",
        "--hidden-import=ultralytics",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--collect-all=ultralytics",
        "--collect-all=PyQt6",
        str(studio_dir / "main.py")
    ]

    icon_path = studio_dir / "icon.ico"
    if icon_path.exists():
        pyinstaller_cmd[13:13] = ["--icon", str(icon_path)]
    
    print("\n[3/5] Running PyInstaller...")
    print(f"Command: {' '.join(pyinstaller_cmd[:5])} ...")
    
    try:
        result = subprocess.run(pyinstaller_cmd, cwd=str(studio_dir), capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[4/5] [OK] Build completed successfully!")
            
            exe_file = dist_dir / "EmberEyeStudio.exe"
            if exe_file.exists():
                file_size = exe_file.stat().st_size / (1024*1024)
                print(f"\n[5/5] [OK] Executable created: {exe_file}")
                print(f"      File size: {file_size:.2f} MB")
                print("\n" + "=" * 60)
                print("Build Complete!")
                print("=" * 60)
                print("\nExecutable location:")
                print(f"  {exe_file}")
                print("\nTo run: Double-click EmberEyeStudio.exe or run:")
                print(f"  {exe_file}")
                return True
            else:
                print(f"[ERROR] Executable not found at {exe_file}")
                return False
        else:
            print("[ERROR] Build failed!")
            if result.stdout:
                print("PyInstaller stdout:")
                print(result.stdout)
            if result.stderr:
                print("PyInstaller stderr:")
                print(result.stderr)
            return False
            
    except Exception as e:
        print(f"[ERROR] Error building installer: {e}")
        return False

if __name__ == "__main__":
    guard_legacy_usage()
    success = build_installer()
    sys.exit(0 if success else 1)

