
import sys
import os
import platform
import logging

# Suppress Qt stylesheet warnings about unknown properties
# This prevents console spam and potential exe build issues
os.environ['QT_LOGGING_RULES'] = '*=false'
os.environ['QT_DEBUG_PLUGINS'] = '0'

# Disable all Qt warnings at the Qt level
import warnings
warnings.filterwarnings('ignore')

# Setup crash logger first for debugging
from crash_logger import setup_crash_logger
setup_crash_logger()

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
from ee_loginwindow import EELoginWindow
from error_logger import get_error_logger
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
    
    login = EELoginWindow()
    
    # Connect signal properly
    def handle_login_success(dashboard):
        dashboard.show()
        login.hide()
    
    login.success.connect(handle_login_success)
    
    login.show()
    
    try:
        exit_code = app.exec_()
    except Exception as e:
        print(f"Application error: {str(e)}")
        exit_code = 1
    finally:
        # Release lock on exit
        if lock_file:
            try:
                fcntl.lockf(lock_file, fcntl.LOCK_UN)
                lock_file.close()
                if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)
            except Exception as e:
                print(f"Lock cleanup error: {e}")
        sys.exit(exit_code)