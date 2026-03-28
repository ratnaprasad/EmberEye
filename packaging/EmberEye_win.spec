# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

# SPECPATH is set by PyInstaller to the directory containing this spec file.
# Project root is one level up from packaging/.
PROJ = os.path.dirname(SPECPATH)

# Minimal Windows spec excluding torch/ultralytics to avoid DLL init errors
datas = [
    (os.path.join(PROJ, 'logo.png'), '.'),
    (os.path.join(PROJ, 'stream_config.example.json'), '.'),
    (os.path.join(PROJ, 'training_config.json'), '.'),
]

# Include annotations folder if it exists (for training support)
if os.path.isdir(os.path.join(PROJ, 'annotations')):
    datas.append((os.path.join(PROJ, 'annotations'), 'annotations'))

binaries = []
hiddenimports = [
    # Top-level modules (for backward compatibility)
    'video_widget', 'main_window', 'stream_config', 'streamconfig_dialog',
    'sensor_fusion', 'baseline_manager', 'pfds_manager', 'database_manager',
    'device_status_manager', 'error_logger', 'crash_logger', 'theme_manager',
    'auto_updater', 'calibrationcapture', 'CalibrationWindow', 'camera_calibrator',
    'annotation_tool', 'adaptive_fps', 'metrics', 'vision_detector',
    'vision_logger', 'video_worker',
    # Force Qt WebEngine modules into frozen build.
    'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebChannel',
    'PyQt5.QtPrintSupport', 'PyQt5.QtNetwork'
]

# Collect embereye_base package (ensures all submodules and embereye_base.app.* are available)
tmp_ret = collect_all('embereye_base')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Collect OpenCV assets/hooks
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Collect Qt WebEngine runtime payload (WebEngineProcess + resources/locales).
for pkg_name in ('PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebChannel'):
    try:
        tmp_ret = collect_all(pkg_name)
        datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
    except Exception:
        pass


a = Analysis(
    [os.path.join(PROJ, 'main.py')],
    pathex=[PROJ, os.path.join(PROJ, 'embereye_base')],
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