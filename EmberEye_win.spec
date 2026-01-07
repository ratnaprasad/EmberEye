# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Minimal Windows spec excluding torch/ultralytics to avoid DLL init errors
datas = [('logo.png', '.'), ('stream_config.json', '.')]
binaries = []
hiddenimports = [
    # Top-level modules (for backward compatibility)
    'video_widget', 'main_window', 'stream_config', 'streamconfig_dialog',
    'sensor_fusion', 'baseline_manager', 'pfds_manager', 'database_manager',
    'device_status_manager', 'error_logger', 'crash_logger', 'theme_manager',
    'auto_updater', 'calibrationcapture', 'CalibrationWindow', 'camera_calibrator',
    'annotation_tool', 'adaptive_fps', 'metrics', 'vision_detector',
    'vision_logger', 'video_worker'
]

# Collect embereye package (ensures all submodules and embereye.app.* are available)
tmp_ret = collect_all('embereye')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Collect OpenCV assets/hooks
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=['.', 'embereye'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['ultralytics', 'torch'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EmberEye',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EmberEye',
)