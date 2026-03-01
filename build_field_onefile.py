#!/usr/bin/env python3
"""Build EmberEye Field executable and optional installer.

Usage:
    python build_field_onefile.py --mode onefile
    python build_field_onefile.py --mode onedir
    python build_field_onefile.py --mode onedir --installer
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ONEFILE_SPEC_FILE = 'EmberEye_Field_OneFile.spec'
ONEDIR_SPEC_FILE = 'EmberEye_Field_OneDir.spec'
ONEFILE_ISS_FILE = Path('installer') / 'EmberEyeFieldSetup.iss'
ONEDIR_ISS_FILE = Path('installer') / 'EmberEyeFieldSetup_Onedir.iss'


def run(cmd):
    print(f"[RUN] {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print('[OK] PyInstaller available')
    except Exception:
        print('[INFO] Installing PyInstaller...')
        run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])


def ensure_icon():
    logo_png = Path('logo.png')
    logo_ico = Path('logo.ico')
    if logo_ico.exists() or not logo_png.exists():
        return
    try:
        from generate_icon import generate_icon

        print('[INFO] Generating logo.ico...')
        generate_icon()
    except Exception as exc:
        print(f'[WARN] Could not generate logo.ico: {exc}')


def clean_build_artifacts():
    for path in ('build', 'dist'):
        p = Path(path)
        if p.exists():
            print(f'[CLEAN] Removing {path}/')
            shutil.rmtree(p, ignore_errors=True)


def build_artifact(mode: str):
    if mode == 'onefile':
        spec_file = ONEFILE_SPEC_FILE
        expected_artifact = Path('dist') / 'EmberEye-Field-OneFile.exe'
    elif mode == 'onedir':
        spec_file = ONEDIR_SPEC_FILE
        expected_artifact = Path('dist') / 'EmberEye-Field-GPU'
    else:
        raise ValueError(f'Unsupported mode: {mode}')

    if not Path(spec_file).exists():
        raise FileNotFoundError(f'Missing spec file: {spec_file}')

    clean_build_artifacts()
    run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', spec_file])

    if not expected_artifact.exists():
        raise RuntimeError(f'Build finished but artifact not found: {expected_artifact}')

    print(f'[SUCCESS] Built {expected_artifact}')
    return expected_artifact


def build_installer(mode: str):
    iss_file = ONEFILE_ISS_FILE if mode == 'onefile' else ONEDIR_ISS_FILE

    if not iss_file.exists():
        raise FileNotFoundError(f'Missing installer script: {iss_file}')

    iscc = shutil.which('ISCC.exe')
    if not iscc:
        print('[WARN] Inno Setup compiler (ISCC.exe) not found in PATH.')
        print(f'[INFO] Compile manually: "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe" "{iss_file}"')
        return

    run([iscc, str(iss_file)])
    print('[SUCCESS] Installer compiled via Inno Setup')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['onefile', 'onedir'], default='onedir', help='Build mode (onedir recommended for GPU torch builds).')
    parser.add_argument('--installer', action='store_true', help='Build setup wizard (requires Inno Setup ISCC.exe)')
    args = parser.parse_args()

    ensure_pyinstaller()
    ensure_icon()
    build_artifact(args.mode)

    if args.installer:
        build_installer(args.mode)
