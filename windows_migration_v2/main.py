
import sys
import os
import platform

# Platform-specific imports
if platform.system() != 'Windows':
    import fcntl

from PyQt5.QtWidgets import (
    QApplication, QMessageBox
)
from PyQt5.QtCore import (
    Qt
)
from ee_loginwindow import EELoginWindow
from error_logger import get_error_logger

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
                           "EmberEye is already running. Please close the existing instance first.")
        sys.exit(1)
    
    # Set High DPI attributes first
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Exception handling with logging
    def _ex_hook(etype, value, tb):
        get_error_logger().log('UNCAUGHT', f"{etype.__name__}: {value}")
        QMessageBox.critical(None, "Error", f"{etype.__name__}: {value}")
    sys.excepthook = _ex_hook
    
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