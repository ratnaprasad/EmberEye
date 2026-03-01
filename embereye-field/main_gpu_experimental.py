
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
        base_candidates = [
            base_path,
            base_path / "_internal",
            base_path / "Lib" / "site-packages",
        ]
        torch_lib_candidates = [
            base_path / "Lib" / "site-packages" / "torch" / "lib",
            base_path / "torch" / "lib",
            base_path / "_internal" / "torch" / "lib",
        ]

        torch_lib_path = next((p for p in torch_lib_candidates if p.exists()), None)
        if torch_lib_path is None:
            continue

        dll_dirs = [p for p in (base_candidates + [torch_lib_path]) if p.exists()]
        path_value = os.environ.get("PATH", "")
        for dll_dir in dll_dirs:
            dll_dir_str = str(dll_dir)
            if dll_dir_str not in path_value:
                path_value = dll_dir_str + os.pathsep + path_value
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(dll_dir_str)
                except Exception:
                    pass

        os.environ["PATH"] = path_value
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
        os.environ["EMBEREYE_FORCE_CPU"] = "1"
        device_label = "CPU"
except Exception as e:
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
    from crash_logger import setup_crash_logger
    setup_crash_logger()
except ImportError:
    pass
