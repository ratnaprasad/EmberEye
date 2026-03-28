"""
EmberEye Studio - Main Entry Point
Desktop application for model training, dataset management, and deployment

Usage:
    python main.py
"""

import sys
import os
from pathlib import Path

# Setup DLL paths for PyTorch CUDA before any imports
# This ensures torch DLLs are found even when the venv is not activated
try:
    repo_root = Path(__file__).parent.parent.resolve()
    candidates = []
    if getattr(sys, "frozen", False):
        # In PyInstaller frozen apps, sys._MEIPASS points to _internal folder
        meipass = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        candidates.append(meipass)  # This is _internal, so torch/lib is directly inside
    env_venv = os.environ.get("EMBEREYE_VENV_PATH")
    if env_venv:
        candidates.append(Path(env_venv))
    candidates.append(repo_root / ".venv")
    candidates.append(Path(sys.executable).parent.parent)

    for base_path in candidates:
        torch_lib_candidates = [
            base_path / "Lib" / "site-packages" / "torch" / "lib",  # venv layout
            base_path / "torch" / "lib",                             # frozen app or direct installation
        ]

        torch_lib_path = next((p for p in torch_lib_candidates if p.exists()), None)
        if torch_lib_path is None:
            continue

        torch_lib_str = str(torch_lib_path)
        if torch_lib_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = torch_lib_str + os.pathsep + os.environ.get("PATH", "")

        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(torch_lib_str)
            except Exception:
                pass
        break
except Exception as e:
    print(f"Warning: Could not setup torch DLL paths: {e}")

# Preload torch before Qt to avoid DLL conflicts
try:
    import torch  # noqa: F401
except Exception as e:
    print(f"Warning: torch preload failed: {e}")

# Ensure studio directory is in path first (before parent)
STUDIO_DIR = Path(__file__).parent.absolute()
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

# Add parent directory for shared modules
BASE_DIR = Path(__file__).parent.parent.absolute()
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))


from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt

# Import studio components (local to this directory)
from studio_db_manager import StudioDatabaseManager
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
            
            return self.app.exec()
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
