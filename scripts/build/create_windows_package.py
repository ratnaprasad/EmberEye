#!/usr/bin/env python3
"""Build a Windows deployment ZIP including all required modules.
Run: python create_windows_package.py
"""
import os, zipfile, datetime, sys

CORE_FILES = [
    "main.py", "main_window.py", "video_widget.py", "video_worker.py",
    "sensor_server.py", "tcp_sensor_server.py",
    "baseline_manager.py", "embereye_base/core/pfds_manager.py", "database_manager.py",
    "embereye_base/core/stream_config.py", "embereye_base/app/streamconfig_dialog.py", "embereye_base/app/streamconfig_editdialog.py",
    "ee_loginwindow.py", "embereye_base/app/user_creation.py", "password_reset.py",
    "license_dialog.py", "license_generator.py", "activationkey_generator.py",
    "licensegenerator_client.py", "setup_wizard.py",
    "camera_calibrator.py", "calibrationcapture.py", "CalibrationWindow.py",
    "embereye_base/app/vendoredata.py", "embereye_base/app/vendorepojo.py", "resource_helper.py",
    "crash_logger.py", "embereye_base/utils/tcp_logger.py", "embereye_base/utils/tcp_server_logger.py", "error_logger.py",
    "dashboardapp_working.py", "embereye_base/app/steam_tester.py",
    "test_client.py",
    # Vision & adaptive modules
    "embereye_base/core/vision_detector.py", "adaptive_fps.py", "metrics.py",
    # Modular fusion engine
    "embereye_base/core/fusion/fusion_engine.py",
    "embereye_base/core/fusion/fusion_orchestrator.py",
    "embereye_base/core/fusion/detectors/base_detector.py",
    "embereye_base/core/fusion/detectors/smoke_detector.py",
    "embereye_base/core/fusion/detectors/flame_analog_detector.py",
    "embereye_base/core/fusion/detectors/flame_digital_detector.py",
    "embereye_base/core/fusion/detectors/thermal_detector.py",
    "embereye_base/core/fusion/detectors/vision_detector.py",
    "embereye_base/core/fusion/detectors/gas_detector.py",
    # Gas sensor module
    "gas_sensor.py"
]

TEST_FILES = [
    "simulators/emberhawk_simulator.py", "tcp_sensor_load_test.py",
    "test_embereye_suite_fixed.py", "test_ai_sensor_components.py",
    "test_ui_workflows.py", "test_auth_user_management.py"
]

DOC_FILES = [
    "requirements.txt", "EmberEye.spec", "packaging/EmberEye_win.spec",
    "BUILD_GUIDE.md", "BUILD_WINDOWS.md", "DISTRIBUTION.md",
    "THERMAL_GRID_FEATURE.md", "README_WINDOWS_MIGRATION.md",
    "TESTING_INDEX.md", "TESTING_QUICK_START.md",
    "TESTING_INFRASTRUCTURE_SUMMARY.md", "TESTING_STATUS_READY.md",
    "WINDOWS_PACKAGE_README.md", "WINDOWS_DEPLOYMENT_GUIDE.md"
]

CONFIG_FILES = ["stream_config.example.json", "users.db"]

ALL = CORE_FILES + TEST_FILES + DOC_FILES + CONFIG_FILES


def build():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"EmberEye_Windows_Complete_{ts}_FULL.zip"
    print(f"Creating package: {zip_name}")
    missing = []
    added = 0
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in ALL:
            if os.path.exists(f):
                z.write(f, f)
                print(f"✓ {f}")
                added += 1
            else:
                print(f"✗ {f} (missing)")
                missing.append(f)
        # images directory
        if os.path.isdir('images'):
            for root, _, files in os.walk('images'):
                for file in files:
                    p = os.path.join(root, file)
                    z.write(p, p)
            print("✓ images/ directory")
        else:
            print("✗ images/ directory (missing)")
    size_mb = os.path.getsize(zip_name)/(1024*1024)
    print("="*70)
    print(f"Added files: {added}, Missing: {len(missing)}, Size: {size_mb:.2f} MB")

    # Quick verification of critical imports
    print("Verifying critical modules...")
    with zipfile.ZipFile(zip_name, 'r') as z:
        def contains(path, snippet):
            try:
                return snippet in z.read(path).decode('utf-8')
            except Exception:
                return False
        print("WebSocket loop fix:", "OK" if contains("main_window.py", "not self.loop.is_running()") else "MISSING")
        print(
            "Vision detector present:",
            "OK" if "embereye_base/core/vision_detector.py" in z.namelist() else "MISSING",
        )
        print("Adaptive FPS present:", "OK" if "adaptive_fps.py" in z.namelist() else "MISSING")
        print("Metrics present:", "OK" if "metrics.py" in z.namelist() else "MISSING")
        print("Gas sensor present:", "OK" if "gas_sensor.py" in z.namelist() else "MISSING")
    print("Package ready:", zip_name)
    return zip_name

if __name__ == '__main__':
    build()
