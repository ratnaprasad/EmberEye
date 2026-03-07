import os
import sys
from pathlib import Path


def _candidate_torch_lib_paths() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if meipass:
            candidates.append(meipass / "torch" / "lib")

    env_venv = os.environ.get("EMBEREYE_VENV_PATH")
    if env_venv:
        venv_path = Path(env_venv)
        candidates.append(venv_path / "Lib" / "site-packages" / "torch" / "lib")

    exe_parent = Path(sys.executable).resolve().parent
    candidates.append(exe_parent / "torch" / "lib")

    # Preserve order while removing duplicates
    seen: set[str] = set()
    unique_paths: list[Path] = []
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique_paths.append(path)

    return unique_paths


def _prepend_to_path(path_str: str) -> None:
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    if path_str not in parts:
        os.environ["PATH"] = path_str + os.pathsep + current


def _try_preload_cuda_dlls(torch_lib: Path) -> None:
    if sys.platform != "win32":
        return

    try:
        import ctypes
    except Exception:
        return

    critical_dlls = [
        "cudart64_12.dll",
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudnn64_9.dll",
        "c10_cuda.dll",
    ]
    for dll_name in critical_dlls:
        dll_path = torch_lib / dll_name
        if dll_path.exists():
            try:
                ctypes.WinDLL(str(dll_path))
            except Exception:
                # Continue best-effort; torch may still load remaining deps.
                pass


def configure_cuda_runtime() -> None:
    if not getattr(sys, "frozen", False):
        return

    os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")

    for torch_lib in _candidate_torch_lib_paths():
        if not torch_lib.exists():
            continue

        torch_lib_str = str(torch_lib)
        _prepend_to_path(torch_lib_str)

        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(torch_lib_str)
            except Exception:
                pass

        # Helpful env vars for downstream checks/debugging
        os.environ.setdefault("CUDA_PATH", str(torch_lib.parent))
        os.environ.setdefault("CUDA_HOME", str(torch_lib.parent))
        os.environ["EMBEREYE_TORCH_LIB"] = torch_lib_str

        _try_preload_cuda_dlls(torch_lib)
        break


configure_cuda_runtime()