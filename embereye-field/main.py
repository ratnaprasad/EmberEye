
import sys
import os
from pathlib import Path

# Setup DLL paths for PyTorch before any Qt/YOLO imports
# This mirrors Studio startup to avoid DLL init failures on Windows.
try:
    repo_root = Path(__file__).parent.parent.resolve()
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        candidates.append(meipass)
    env_venv = os.environ.get("EMBEREYE_VENV_PATH")
    if env_venv:
        candidates.append(Path(env_venv))
    candidates.append(repo_root / ".venv")
    candidates.append(Path(sys.executable).parent.parent)

    for base_path in candidates:
        torch_lib_candidates = [
            base_path / "Lib" / "site-packages" / "torch" / "lib",
            base_path / "torch" / "lib",
        ]

        torch_lib_path = next((p for p in torch_lib_candidates if p.exists()), None)
        if torch_lib_path is None:
            continue

        torch_lib_str = str(torch_lib_path)
        if torch_lib_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = torch_lib_str + os.pathsep + os.environ.get("PATH", "")

        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(torch_lib_str)
            except Exception:
                pass
        break
except Exception as e:
    print(f"Warning: Could not setup torch DLL paths: {e}")

# Preload torch before Qt to avoid DLL conflicts and set device fallback info
device_label = "CPU"
try:
    import torch  # noqa: F401
    force_cpu = os.environ.get("EMBEREYE_FORCE_CPU", "").strip().lower() in ("1", "true", "yes")
    if force_cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        device_label = "CPU (forced)"
    elif torch.cuda.is_available():
        device_label = "GPU"
    else:
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        device_label = "CPU"
except Exception as e:
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    device_label = "CPU"
    print(f"Warning: torch preload failed: {e}")

os.environ.setdefault("EMBEREYE_DEVICE", device_label)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# EmberEye Field Edition - Monitoring and Detection Only
# No training dependencies required
os.environ.setdefault('EMBEREYE_FIELD', '1')

import platform
import logging

# Configure logging to output to console for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Suppress Qt stylesheet warnings about unknown properties
# This prevents console spam and potential exe build issues
os.environ['QT_LOGGING_RULES'] = '*=false'
os.environ['QT_DEBUG_PLUGINS'] = '0'

# Disable all Qt warnings at the Qt level
import warnings
warnings.filterwarnings('ignore')

# Setup crash logger first for debugging
try:
    from crash_logger import setup_crash_logger
    setup_crash_logger()
except ImportError:
    pass

# Ensure runtime folders exist
try:
    from shared.emberkit.resource_helper import ensure_runtime_folders
    workspace_dir = ensure_runtime_folders()
    print(f"[INIT] Workspace directory: {workspace_dir}")
except ImportError:
    workspace_dir = os.path.dirname(__file__)
    print(f"[INIT] Using default workspace: {workspace_dir}")

# Check for updates in background (non-blocking) - DISABLED FOR OFFLINE MODE
try:
    from auto_updater import auto_check_updates_background
    # auto_check_updates_background()  # Disabled - not needed for offline use
except Exception as e:
    pass  # Silently ignore updater errors

# Platform-specific imports
if platform.system() != 'Windows':
    import fcntl

from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QDialog
)
from PyQt5.QtCore import (
    Qt, QThread
)
try:
    from ee_loginwindow import EELoginWindow
except ImportError:
    EELoginWindow = None

from shared.emberkit.error_logger import get_error_logger
# License module may be absent in checkpoint; guard imports
try:
    from license_module.core import LicenseClient, LicenseNotFoundError
    from license_module.ui import LicenseEntryDialog, LicenseRenewalDialog
except Exception:
    LicenseClient = None
    class LicenseNotFoundError(Exception):
        pass
    # Fallback dialog stubs
    class LicenseEntryDialog(QDialog):
        def __init__(self, *args, **kwargs):
            super().__init__()
        def exec_(self):
            return QDialog.Rejected
    class LicenseRenewalDialog(QDialog):
        def __init__(self, *args, **kwargs):
            super().__init__()
        def exec_(self):
            return QDialog.Rejected

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Single instance check using lock file
    lock_file_path = os.path.join(os.path.dirname(__file__), '.embereve.lock')
    lock_file = None
    
    try:
        lock_file = open(lock_file_path, 'w')
        
        if platform.system() == 'Windows':
            # Windows: Use file existence as lock (msvcrt alternative)
            import msvcrt
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except IOError:
                raise IOError("Lock already held")
        else:
            # Unix/Linux/macOS: Use fcntl
            fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # Lock already held - another instance is running
        app = QApplication(sys.argv)
        QMessageBox.warning(None, "Already Running", 
                           "Ember Eye is already running. Please close the existing instance first.")
        sys.exit(1)
    
    # Set High DPI attributes first
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Exception handling with logging (thread-safe)
    def _ex_hook(etype, value, tb):
        from PyQt5.QtCore import QMetaObject, Q_ARG
        get_error_logger().log('UNCAUGHT', f"{etype.__name__}: {value}")
        # Only show message box if in main thread
        try:
            if QThread.currentThread() == QApplication.instance().thread():
                QMessageBox.critical(None, "Error", f"{etype.__name__}: {value}")
            else:
                print(f"Error in worker thread: {etype.__name__}: {value}")
        except:
            print(f"Error: {etype.__name__}: {value}")
    sys.excepthook = _ex_hook
    
    # ===== License Check =====
    # DEVELOPMENT MODE: Skip license check for testing
    def check_license_at_startup():
        """
        Check license status at startup.
        DEVELOPMENT: Skipped for testing. Set SKIP_LICENSE_CHECK=false to enable.
        """
        import os
        skip_license = os.environ.get('SKIP_LICENSE_CHECK', 'true').lower() == 'true'
        
        if skip_license:
            print("[DEV] License check skipped - set SKIP_LICENSE_CHECK=false to enable")
            return True
        
        # If license module unavailable, allow app to proceed in dev mode
        if LicenseClient is None:
            return True
        try:
            license_client = LicenseClient()
            status, license_data = license_client.check_license_status()
            
            if status == "VALID":
                # License is valid, allow app to proceed
                return True
            
            elif status == "EXPIRING_SOON":
                # License expiring soon - warn but allow app
                dialog = LicenseRenewalDialog(license_data)
                result = dialog.exec_()
                if result == QDialog.Accepted:
                    # User wants to enter new license
                    entry_dialog = LicenseEntryDialog()
                    entry_dialog.exec_()
                return True
            
            elif status == "EXPIRED":
                # License expired - block app
                license_info = license_client.get_license_info()
                dialog = LicenseRenewalDialog(license_info)
                result = dialog.exec_()
                if result == QDialog.Accepted:
                    # User wants to enter new license
                    entry_dialog = LicenseEntryDialog()
                    if entry_dialog.exec_() == QDialog.Accepted:
                        # Re-check license after entry
                        return check_license_at_startup()
                return False
            
            else:  # NOT_FOUND
                # No license found - prompt for entry
                entry_dialog = LicenseEntryDialog()
                result = entry_dialog.exec_()
                if result == QDialog.Accepted:
                    # Re-check license after entry
                    return check_license_at_startup()
                return False
                
        except Exception as e:
            print(f"License check error: {e}")
            QMessageBox.critical(None, "License Error", f"License validation failed: {e}")
            return False
    
    # Run license check
    if not check_license_at_startup():
        print("License validation failed - exiting")
        sys.exit(1)
    
    if EELoginWindow is None:
        print("[ERROR] ❌ EELoginWindow failed to import!")
        print("[ERROR] Make sure ee_loginwindow.py is in the root directory")
        sys.exit(1)
    
    print("[LOGIN] Creating login window...")
    try:
        login = EELoginWindow()
        print("[LOGIN] Login window created successfully")
    except Exception as e:
        print(f"[LOGIN] ❌ Failed to create login window: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Connect signal properly
    def handle_login_success(dashboard):
        dashboard.show()
        login.hide()
    
    login.success.connect(handle_login_success)
    
    print("[LOGIN] Showing login window...")
    login.show()
    print("[LOGIN] Login window shown. Starting app event loop...")
    
    try:
        exit_code = app.exec_()
    except Exception as e:
        print(f"Application error: {str(e)}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        # Release lock on exit
        if lock_file:
            try:
                if platform.system() == 'Windows':
                    # Windows: Release lock using msvcrt
                    try:
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except:
                        pass
                else:
                    # Unix/Linux/macOS: Use fcntl
                    fcntl.lockf(lock_file, fcntl.LOCK_UN)
                lock_file.close()
                if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)
            except Exception as e:
                print(f"Lock cleanup error: {e}")
        sys.exit(exit_code)