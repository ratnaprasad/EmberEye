
import sys
import os
from pathlib import Path
import ctypes
import io

# --------------------------------------------------------------------------
# Force UTF-8 stdout/stderr for frozen builds to prevent UnicodeEncodeError
# when printing emoji or non-ASCII characters to the Windows console.
# --------------------------------------------------------------------------
if getattr(sys, "frozen", False) and sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_DLL_DIR_HANDLES = []

# --------------------------------------------------------------------------
# Early runtime setup for frozen (PyInstaller) builds on Windows.
# The packaged app runs inference in CPU mode, but the installed torch wheel
# still depends on its bundled CUDA-adjacent DLL set at import time. Do not
# quarantine those DLLs unless explicitly requested for debugging.
# --------------------------------------------------------------------------
if getattr(sys, "frozen", False) and sys.platform == "win32":
    os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["EMBEREYE_FORCE_CPU"] = "1"
    os.environ.setdefault("EMBEREYE_QUARANTINE_CUDA_DLLS", "0")


def _append_bootstrap_log(message: str) -> None:
    timestamped = message.rstrip() + "\n"
    candidate_paths = []
    try:
        if getattr(sys, "frozen", False):
            home_dir = os.path.expanduser("~")
            candidate_paths.append(os.path.join(home_dir, ".embereye", "field_bootstrap.log"))
            candidate_paths.append(os.path.join(os.path.dirname(sys.executable), "field_bootstrap.log"))
        else:
            candidate_paths.append(os.path.abspath("field_bootstrap.log"))
    except Exception:
        return

    seen = set()
    for log_path in candidate_paths:
        try:
            norm_path = os.path.normcase(os.path.abspath(log_path))
            if norm_path in seen:
                continue
            seen.add(norm_path)
            parent_dir = os.path.dirname(log_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as bootstrap_log:
                bootstrap_log.write(timestamped)
        except Exception:
            continue


def _restore_quarantined_torch_dlls() -> None:
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return

    candidate_dirs = []
    try:
        candidate_dirs.append(Path(sys.executable).parent / "_internal" / "torch" / "lib")
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate_dirs.append(meipass / "torch" / "lib")
        candidate_dirs.append(meipass / "_internal" / "torch" / "lib")
    except Exception:
        pass

    seen_dirs = set()
    restored = 0
    for lib_dir in candidate_dirs:
        try:
            lib_dir = lib_dir.resolve()
        except Exception:
            lib_dir = Path(lib_dir)

        dir_key = os.path.normcase(str(lib_dir))
        if dir_key in seen_dirs or not lib_dir.exists():
            continue
        seen_dirs.add(dir_key)

        for disabled_path in lib_dir.glob("*.dll.disabled"):
            original_path = disabled_path.with_suffix("")
            try:
                if original_path.exists():
                    disabled_path.unlink(missing_ok=True)
                    continue
                disabled_path.rename(original_path)
                restored += 1
            except Exception as exc:
                _append_bootstrap_log(f"[BOOTSTRAP] Failed to restore {disabled_path.name}: {exc!r}")

    if restored:
        _append_bootstrap_log(f"[BOOTSTRAP] Restored {restored} quarantined torch DLLs")


def _disable_bundled_cuda_runtime() -> None:
    # Optional debugging hook: quarantine CUDA DLLs only when explicitly
    # requested. The packaged torch wheel still imports several of these DLLs
    # even in CPU mode, so this must stay opt-in.
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return

    explicit_quarantine = os.environ.get("EMBEREYE_QUARANTINE_CUDA_DLLS", "").strip().lower() in ("1", "true", "yes")

    if not explicit_quarantine:
        return

    _append_bootstrap_log("[BOOTSTRAP] Starting CUDA DLL quarantine...")

    dll_markers = (
        "c10_cuda",
        "caffe2_nvrtc",
        "cublas",
        "cudart",
        "cudnn",
        "cufft",
        "cupti",
        "curand",
        "cusolver",
        "cusparse",
        "nvjitlink",
        "nvperf",
        "nvrtc",
        "nvtoolsext",
        "torch_cuda",
    )

    candidate_dirs = []
    try:
        candidate_dirs.append(Path(sys.executable).parent / "_internal" / "torch" / "lib")
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate_dirs.append(meipass / "torch" / "lib")
        candidate_dirs.append(meipass / "_internal" / "torch" / "lib")
    except Exception:
        pass

    seen_dirs = set()
    for lib_dir in candidate_dirs:
        try:
            lib_dir = lib_dir.resolve()
        except Exception:
            lib_dir = Path(lib_dir)
        dir_key = os.path.normcase(str(lib_dir))
        if dir_key in seen_dirs or not lib_dir.exists():
            continue
        seen_dirs.add(dir_key)

        for dll_path in lib_dir.glob("*.dll"):
            lower_name = dll_path.name.lower()
            if not any(marker in lower_name for marker in dll_markers):
                continue
            disabled_path = dll_path.with_suffix(dll_path.suffix + ".disabled")
            try:
                if disabled_path.exists():
                    dll_path.unlink(missing_ok=True)
                    _append_bootstrap_log(f"[BOOTSTRAP] Removed already-disabled CUDA DLL duplicate: {dll_path}")
                else:
                    dll_path.rename(disabled_path)
                    _append_bootstrap_log(f"[BOOTSTRAP] Disabled CUDA DLL: {dll_path.name}")
            except Exception as exc:
                _append_bootstrap_log(f"[BOOTSTRAP] Failed to disable {dll_path.name}: {exc!r}")


_restore_quarantined_torch_dlls()
_disable_bundled_cuda_runtime()


def _check_windows_runtime_dependencies() -> None:
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return

    # If these fail, c10.dll will fail even in CPU-only torch builds.
    runtime_dlls = ("ucrtbase.dll", "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
    for dll_name in runtime_dlls:
        try:
            ctypes.CDLL(dll_name)
            _append_bootstrap_log(f"[BOOTSTRAP] Runtime OK: {dll_name}")
        except OSError as exc:
            _append_bootstrap_log(f"[BOOTSTRAP] Runtime missing/broken {dll_name}: {exc}")

def _preload_torch_runtime_dependencies(torch_lib_path: Path, base_path: Path) -> None:
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return

    # ONLY preload CRT DLLs (vcruntime, msvcp).
    # torch's own _load_dll_libraries() handles everything else properly.
    # Trying to manually preload c10.dll or other libs circumvents torch's
    # LoadLibraryExW logic which has proper error context.
    
    crt_only = [
        base_path / "vcruntime140.dll",
        base_path / "msvcp140.dll",
        base_path / "vcruntime140_1.dll",
    ]
    
    for dll_path in crt_only:
        if not dll_path.exists():
            continue
        try:
            ctypes.CDLL(str(dll_path))
            _append_bootstrap_log(f"[BOOTSTRAP] Preloaded CRT {dll_path.name}")
        except Exception as exc:
            _append_bootstrap_log(f"[BOOTSTRAP] Failed preload CRT {dll_path.name}: {exc!r}")

# Setup DLL paths for PyTorch before any Qt/YOLO imports.
# CRITICAL: Follow torch's own _load_dll_libraries() exactly:
# 1. Register ALL dll directories with os.add_dll_directory()
# 2. Preload only CRT (vcruntime/msvcp) to ensure they're initialized
# 3. LET TORCH'S OWN LOADER handle c10.dll via LoadLibraryExW with proper error handling
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
            base_path / "_internal" / "torch" / "lib",
        ]

        torch_lib_path = next((p for p in torch_lib_candidates if p.exists()), None)
        if torch_lib_path is None:
            continue

        # Register relevant directories and KEEP handles alive; otherwise
        # Windows may drop the search path before torch import runs.
        dll_dirs = [
            torch_lib_path,
            base_path,
            base_path / "Lib" / "site-packages",
            Path(sys.exec_prefix) / "Library" / "bin",
            Path(sys.exec_prefix) / "bin",
        ]

        # De-duplicate while preserving order.
        seen = set()
        deduped = []
        for p in dll_dirs:
            key = os.path.normcase(str(p))
            if key in seen or not p.exists():
                continue
            seen.add(key)
            deduped.append(p)
        dll_dirs = deduped
        
        path_value = os.environ.get("PATH", "")
        for dll_dir in dll_dirs:
            dll_dir_str = str(dll_dir)
            if dll_dir_str not in path_value:
                path_value = dll_dir_str + os.pathsep + path_value
            if hasattr(os, "add_dll_directory"):
                try:
                    handle = os.add_dll_directory(dll_dir_str)
                    _DLL_DIR_HANDLES.append(handle)
                    _append_bootstrap_log(f"[BOOTSTRAP] Registered DLL dir: {dll_dir_str}")
                except Exception as e:
                    _append_bootstrap_log(f"[BOOTSTRAP] Failed register DLL dir {dll_dir_str}: {e}")

        os.environ["PATH"] = path_value
        
        # Only preload CRT DLLs (which torch does too)
        _preload_torch_runtime_dependencies(torch_lib_path, base_path)
        break
except Exception as e:
    _append_bootstrap_log(f"[BOOTSTRAP] DLL path setup error: {e}")
    print(f"Warning: Could not setup torch DLL paths: {e}")

# Preload torch before Qt to avoid DLL conflicts and set device fallback info
device_label = "CPU"
try:
    torch_preloaded = os.environ.get("EMBEREYE_TORCH_PRELOADED") == "1"
    if torch_preloaded:
        _append_bootstrap_log("[BOOTSTRAP] torch already preloaded by runtime hook")
    else:
        _check_windows_runtime_dependencies()
        _append_bootstrap_log("[BOOTSTRAP] Attempting import torch...")
        import torch  # noqa: F401
        _append_bootstrap_log("[BOOTSTRAP] torch imported OK")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["EMBEREYE_FORCE_CPU"] = "1"
    device_label = "CPU (forced)"
    _append_bootstrap_log(f"[BOOTSTRAP] device_label={device_label}")
except OSError as e:
    # Catch DLL init failures (error 1114) during torch import / CUDA probe
    _append_bootstrap_log(f"[BOOTSTRAP] torch import OSError: {type(e).__name__}: {e}")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["EMBEREYE_FORCE_CPU"] = "1"
    device_label = "CPU"
    print(f"Warning: torch preload OSError (forcing CPU): {e}")
except Exception as e:
    _append_bootstrap_log(f"[BOOTSTRAP] torch import Exception: {type(e).__name__}: {e}")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["EMBEREYE_FORCE_CPU"] = "1"
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
    from embereye_base.utils.crash_logger import setup_crash_logger
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
    from embereye_base.core.auto_updater import auto_check_updates_background
    # auto_check_updates_background()  # Disabled - not needed for offline use
except Exception as e:
    pass  # Silently ignore updater errors

# Platform-specific imports
if platform.system() != 'Windows':
    import fcntl

from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QDialog
)
from PyQt6.QtCore import (
    Qt, QThread
)
try:
    from embereye_base.app.ee_loginwindow import EELoginWindow
except Exception as _login_import_err:
    EELoginWindow = None
    print(f"[ERROR] EELoginWindow import failed: {_login_import_err}")
    import traceback; traceback.print_exc()

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
        def exec(self):
            return QDialog.DialogCode.Rejected
    class LicenseRenewalDialog(QDialog):
        def __init__(self, *args, **kwargs):
            super().__init__()
        def exec(self):
            return QDialog.DialogCode.Rejected

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Windows-only hard single-instance guard using a named mutex.
    # This avoids split runtime state when two app processes start together.
    app_mutex = None
    if platform.system() == 'Windows':
        try:
            kernel32 = ctypes.windll.kernel32
            mutex_name = "Global\\EmberEyeFieldSingleInstance"
            app_mutex = kernel32.CreateMutexW(None, False, mutex_name)
            if not app_mutex:
                raise OSError("CreateMutexW failed")
            ERROR_ALREADY_EXISTS = 183
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                app = QApplication(sys.argv)
                QMessageBox.warning(None, "Already Running", "Ember Eye is already running. Please close the existing instance first.")
                sys.exit(1)
        except Exception:
            # Fall back to legacy file lock below.
            app_mutex = None

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
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Exception handling with logging (thread-safe)
    def _ex_hook(etype, value, tb):
        from PyQt6.QtCore import QMetaObject, Q_ARG
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
                result = dialog.exec()
                if result == QDialog.DialogCode.Accepted:
                    # User wants to enter new license
                    entry_dialog = LicenseEntryDialog()
                    entry_dialog.exec()
                return True
            
            elif status == "EXPIRED":
                # License expired - block app
                license_info = license_client.get_license_info()
                dialog = LicenseRenewalDialog(license_info)
                result = dialog.exec()
                if result == QDialog.DialogCode.Accepted:
                    # User wants to enter new license
                    entry_dialog = LicenseEntryDialog()
                    if entry_dialog.exec() == QDialog.DialogCode.Accepted:
                        # Re-check license after entry
                        return check_license_at_startup()
                return False
            
            else:  # NOT_FOUND
                # No license found - prompt for entry
                entry_dialog = LicenseEntryDialog()
                result = entry_dialog.exec()
                if result == QDialog.DialogCode.Accepted:
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
        exit_code = app.exec()
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