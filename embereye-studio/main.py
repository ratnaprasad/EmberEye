"""
EmberEye Studio - Main Entry Point
Desktop application for model training, dataset management, and deployment

Usage:
    python main.py
"""

import sys
import os
from pathlib import Path

# Ensure studio directory is in path first (before parent)
STUDIO_DIR = Path(__file__).parent.absolute()
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

# Add parent directory for shared modules
BASE_DIR = Path(__file__).parent.parent.absolute()
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import Qt

# Import studio components (local to this directory)
from database_manager import StudioDatabaseManager
from studio_login import StudioLoginWindow
from studio_main_window import StudioMainWindow


class StudioApplication:
    """Main application coordinator"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.db = StudioDatabaseManager()
        self.login_window = None
        self.main_window = None

    def run(self):
        """Run application"""
        try:
            # Show login window
            self.login_window = StudioLoginWindow(self.db)
            self.login_window.login_success.connect(self.on_login_success)
            self.login_window.show()
            
            return self.app.exec_()
        except Exception as e:
            print(f"Error running application: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def on_login_success(self, username):
        """Handle successful login"""
        try:
            # Hide login window
            if self.login_window:
                self.login_window.hide()
            
            # Show main window
            self.main_window = StudioMainWindow(username)
            self.main_window.show()
            
            # Close login window completely
            if self.login_window:
                self.login_window.close()
                
        except Exception as e:
            print(f"Error on login success: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point"""
    try:
        studio_app = StudioApplication()
        sys.exit(studio_app.run())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
