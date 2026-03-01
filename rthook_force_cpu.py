# PyInstaller runtime hook — runs BEFORE any application code or imports.
# Forces CPU-only mode so that broken/incomplete CUDA DLLs bundled by
# PyInstaller are never loaded, preventing OSError 1114.
import os
import sys

# Only activate for frozen (packaged) builds
if getattr(sys, "frozen", False):
    # Lazy-load CUDA modules so they aren't probed eagerly
    os.environ["CUDA_MODULE_LOADING"] = "LAZY"
    # Try to load the NVIDIA driver DLL to see if CUDA is even possible
    _cuda_ok = False
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.WinDLL("nvcuda.dll")
            _cuda_ok = True
        except (OSError, Exception):
            _cuda_ok = False
    # If the driver isn't accessible, disable CUDA entirely
    if not _cuda_ok:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["EMBEREYE_FORCE_CPU"] = "1"
        os.environ["USE_CUDA"] = "0"
        os.environ["FORCE_CUDA"] = "0"
    # Even with a driver present, bundled CUDA toolkit DLLs often fail.
    # Do a deeper probe: try importing torch and checking CUDA — if that
    # triggers a DLL error, fall back to CPU.
    else:
        try:
            import torch
            if not torch.cuda.is_available():
                os.environ["CUDA_VISIBLE_DEVICES"] = ""
                os.environ["EMBEREYE_FORCE_CPU"] = "1"
        except OSError:
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
            os.environ["EMBEREYE_FORCE_CPU"] = "1"
            os.environ["USE_CUDA"] = "0"
        except Exception:
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
            os.environ["EMBEREYE_FORCE_CPU"] = "1"
