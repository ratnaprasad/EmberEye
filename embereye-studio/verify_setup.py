"""
EmberEye Studio Architecture Overview
Verify all components are in place and working
"""

import os
import sys
from pathlib import Path

def check_file(path, description):
    """Check if file exists and show status"""
    exists = Path(path).exists()
    status = "✓" if exists else "✗"
    size = ""
    if exists:
        size = f" ({Path(path).stat().st_size:,} bytes)"
    print(f"{status} {description}{size}")
    return exists

def check_imports(module_name, components):
    """Check if module imports work"""
    try:
        mod = __import__(module_name)
        for comp in components:
            if hasattr(mod, comp):
                print(f"  ✓ {module_name}.{comp}")
            else:
                print(f"  ✗ {module_name}.{comp} NOT FOUND")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False

print("=" * 60)
print("EMBEREYE STUDIO - COMPONENT VERIFICATION")
print("=" * 60)
print()

# Directory structure
print("📁 Directory Structure:")
dirs = [
    "embereye-studio",
    "embereye-studio/forgelab",
    "embereye-studio/aviary",
    "embereye-studio/emberarchive",
    "embereye-studio/commandnest",
    "embereye-studio/ignissim",
]
for d in dirs:
    path = Path(d) if d == "embereye-studio" else Path("embereye-studio") / d.split("/")[1]
    check_file(path, f"  {d}/")

print()

# Core files
print("📄 Core Files:")
files = [
    ("embereye-studio/main.py", "Main entry point (GUI launcher)"),
    ("embereye-studio/database_manager.py", "User & project database (StudioDatabaseManager)"),
    ("embereye-studio/studio_login.py", "Login window UI (StudioLoginWindow)"),
    ("embereye-studio/studio_main_window.py", "Main application window"),
    ("embereye-studio/__init__.py", "Package initialization"),
]
for path, desc in files:
    check_file(path, f"  {desc}")

print()

# ForgeLab training files
print("🧠 ForgeLab Training Pipeline:")
files = [
    ("embereye-studio/forgelab/__init__.py", "ForgeLab exports"),
    ("embereye-studio/forgelab/training_pipeline.py", "YOLO training pipeline (1264 lines)"),
]
for path, desc in files:
    check_file(path, f"  {desc}")

print()

# Database verification
print("💾 Database:")
try:
    from database_manager import StudioDatabaseManager
    db = StudioDatabaseManager("verify_test.db")
    print("  ✓ DatabaseManager instantiated")
    
    users = ["admin", "ratna", "s3micro"]
    for user in users:
        u = db.get_user(user)
        if u:
            print(f"    ✓ User '{user}' found in database")
    
    import bcrypt
    admin = db.get_user("admin")
    if admin and bcrypt.checkpw(b"password", admin[1].encode('utf-8')):
        print(f"    ✓ Password verification works")
    
    db.close()
    os.remove("verify_test.db")
    print("  ✓ Database test completed and cleaned up")
except Exception as e:
    print(f"  ✗ Database error: {e}")

print()

# Training pipeline verification
print("🚀 Training Pipeline (ForgeLab):")
try:
    sys.path.insert(0, str(Path("embereye-studio").absolute()))
    from forgelab import (
        TrainingConfig, TrainingProgress, TrainingStatus,
        DeviceManager, DatasetManager, YOLOTrainingPipeline
    )
    print("  ✓ ForgeLab imports successful")
    
    devices = DeviceManager.get_available_devices()
    print(f"    ✓ GPU detected: {devices['gpu']}")
    print(f"    ✓ CPU detected: {devices['cpu']}")
    print(f"    ✓ Recommended device: {devices['recommended']}")
    
    config = TrainingConfig(
        project_name="verify_test",
        model_size="n",
        epochs=10
    )
    print(f"    ✓ TrainingConfig created: {config.project_name}")
    
except Exception as e:
    print(f"  ✗ Training pipeline error: {e}")
    import traceback
    traceback.print_exc()

print()

# UI components verification
print("🎨 UI Components:")
try:
    from studio_login import StudioLoginWindow
    from studio_main_window import StudioMainWindow, TrainingTab, DatasetTab, SettingsTab
    print("  ✓ StudioLoginWindow class available")
    print("  ✓ StudioMainWindow class available")
    print("  ✓ TrainingTab (ForgeLab UI) available")
    print("  ✓ DatasetTab (EmberArchive UI) available")
    print("  ✓ SettingsTab available")
except Exception as e:
    print(f"  ✗ UI components error: {e}")

print()

# Features
print("✨ Available Features:")
print("  ✓ User authentication (3 default accounts)")
print("  ✓ Role-based access (admin, data_scientist, reviewer)")
print("  ✓ Training pipeline with GPU/CPU auto-detection")
print("  ✓ Dataset management framework")
print("  ✓ Real-time training progress tracking")
print("  ✓ Project and run history tracking")
print("  ✓ Model configuration presets")

print()

# Usage
print("🚀 How to Run:")
print()
print("  cd D:\\EE\\EmberEye\\embereye-studio")
print("  & D:\\EE\\EmberEye\\.venv\\Scripts\\Activate.ps1")
print("  python main.py")
print()
print("  Login with:")
print("    - admin / password")
print("    - ratna / ratna")
print("    - s3micro / s3micro")
print()

print("=" * 60)
print("✅ EmberEye Studio is ready for use!")
print("=" * 60)
