#!/bin/bash
# Windows onedir build script
# Run this on Windows (git bash, powershell, or cmd)

pyinstaller --clean --noconfirm ^
  --name EmberEye ^
  --onedir ^
  --windowed ^
  --icon logo.png ^
  --paths . ^
  --paths embereye ^
  --add-data "logo.png:." ^
  --hidden-import=video_widget ^
  --hidden-import=main_window ^
  --hidden-import=stream_config ^
  --hidden-import=streamconfig_dialog ^
  --hidden-import=sensor_fusion ^
  --hidden-import=baseline_manager ^
  --hidden-import=pfds_manager ^
  --hidden-import=tcp_server ^
  --hidden-import=database_manager ^
  --hidden-import=device_status_manager ^
  --hidden-import=error_logger ^
  --hidden-import=crash_logger ^
  --hidden-import=theme_manager ^
  --hidden-import=auto_updater ^
  --hidden-import=calibrationcapture ^
  --hidden-import=CalibrationWindow ^
  --hidden-import=camera_calibrator ^
  --hidden-import=annotation_tool ^
  --hidden-import=adaptive_fps ^
  --hidden-import=metrics ^
  --hidden-import=vision_detector ^
  --hidden-import=vision_logger ^
  --hidden-import=video_worker ^
  --collect-all ultralytics ^
  --collect-all torch ^
  --collect-all cv2 ^
  main.py
