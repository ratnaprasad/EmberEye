"""Windows build helper script for EmberEye.

Usage (PowerShell):
  python -m venv .venv
  .venv\Scripts\activate
  pip install --upgrade pip
  pip install -r requirements.txt psutil pywin32
  python build_windows.py

Produces: dist/EmberEye/EmberEye.exe + resources
Then create zip:
  Compress-Archive -Path dist/EmberEye/* -DestinationPath EmberEye_Windows.zip -Force
"""
import os
import subprocess
import sys

SPEC_FILE = 'EmberEye_win.spec'

REQUIRED_MODULES = [
    'PyQt5', 'PyQtWebEngine', 'numpy', 'opencv-python', 'bcrypt', 'websockets', 'passlib', 'cryptography'
]
OPTIONAL_MODULES = ['psutil', 'pywin32']


def run(cmd, shell=False, check=True):
    print(f"[RUN] {cmd}")
    result = subprocess.run(cmd, shell=shell, check=check)
    return result.returncode


def ensure_modules():
    import importlib
    missing = []
    for m in REQUIRED_MODULES + OPTIONAL_MODULES:
        try:
            importlib.import_module(m)
        except Exception:
            missing.append(m)
    if missing:
        print(f"[INFO] Installing missing modules: {missing}")
        run([sys.executable, '-m', 'pip', 'install'] + missing)
    else:
        print("[INFO] All required modules present.")


def generate_icon():
    """Generate logo.ico from logo.png if not exists."""
    if os.path.exists('logo.ico'):
        print('[INFO] logo.ico already exists, skipping generation')
        return
    if not os.path.exists('logo.png'):
        print('[WARN] logo.png not found, skipping icon generation')
        return
    print('[ICON] Generating logo.ico from logo.png...')
    try:
        from generate_icon import generate_icon as _gen
        _gen()
        print('[ICON] Successfully generated logo.ico')
    except Exception as e:
        print(f'[WARN] Icon generation failed: {e}')
        print('[WARN] Continuing build without icon...')


def build():
    if not os.path.exists(SPEC_FILE):
        print(f"[ERROR] Spec file {SPEC_FILE} missing.")
        sys.exit(1)
    
    # Generate icon before build
    generate_icon()
    
    # Clean previous build
    if os.path.isdir('build'):
        print('[CLEAN] Removing build directory')
        import shutil; shutil.rmtree('build', ignore_errors=True)
    if os.path.isdir('dist'):
        print('[CLEAN] Removing dist directory')
        import shutil; shutil.rmtree('dist', ignore_errors=True)

    cmd = [sys.executable, '-m', 'PyInstaller', '--clean', SPEC_FILE]
    run(cmd)
    exe_path = os.path.join('dist', 'EmberEye', 'EmberEye.exe')
    if os.path.exists(exe_path):
        print(f"[SUCCESS] Built: {exe_path}")
        print("Zip with: Compress-Archive -Path dist/EmberEye/* -DestinationPath EmberEye_Windows.zip -Force")
    else:
        print('[FAIL] Build did not produce expected executable.')
        sys.exit(2)


if __name__ == '__main__':
    ensure_modules()
    build()
