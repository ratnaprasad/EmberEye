# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# SPECPATH is set by PyInstaller to the packaging/ directory; project root is one level up.
project_dir = os.path.dirname(SPECPATH)
studio_dir = os.path.join(project_dir, "embereye-studio")

# Collect torch CUDA DLLs and related libs
torch_binaries = []
torch_binaries += collect_dynamic_libs('torch')
torch_binaries += collect_dynamic_libs('torchvision')
torch_binaries += collect_dynamic_libs('torchaudio')

a = Analysis(
    ['embereye-studio\\main.py'],
    pathex=[project_dir, studio_dir],
    binaries=torch_binaries,
    datas=[],
    hiddenimports=[
        'studio_db_manager',
        'studio_login',
        'studio_main_window',
        'torch',
        'torchvision',
        'torchaudio',
        'ultralytics',
        'cv2',
        'numpy',
    ],
    hookspath=[os.path.join(studio_dir, "hooks")],
    hooksconfig={},
    runtime_hooks=[os.path.join(studio_dir, "hooks", "rthook_cuda_setup.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='embereye-studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
