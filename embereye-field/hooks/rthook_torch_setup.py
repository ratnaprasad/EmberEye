import os
import sys
from pathlib import Path
from datetime import datetime

_DLL_DIR_HANDLES = []
_LOG_PATH = Path.home() / ".embereye" / "field_rthook.log"


def _log(message: str) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception:
        pass


def _prepend_path(path_str: str) -> None:
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    if path_str not in parts:
        os.environ["PATH"] = path_str + os.pathsep + current


def _candidate_base_paths() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass_raw = getattr(sys, "_MEIPASS", "")
        if meipass_raw:
            candidates.append(Path(meipass_raw))

    exe_parent = Path(sys.executable).resolve().parent
    candidates.append(exe_parent)
    candidates.append(exe_parent / "_internal")

    env_venv = os.environ.get("EMBEREYE_VENV_PATH")
    if env_venv:
        candidates.append(Path(env_venv))

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _register_dll_dirs() -> None:
    if sys.platform != "win32":
        return

    os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
    os.environ.setdefault("EMBEREYE_QUARANTINE_CUDA_DLLS", "0")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("EMBEREYE_FORCE_CPU", "1")

    _log("[RTHOOK] Starting torch runtime setup")

    for base in _candidate_base_paths():
        dll_dirs = [
            base / "torch" / "lib",
            base / "_internal" / "torch" / "lib",
            base,
            base / "_internal",
            base / "Lib" / "site-packages",
        ]

        for dll_dir in dll_dirs:
            if not dll_dir.exists():
                continue
            dll_dir_str = str(dll_dir)
            _prepend_path(dll_dir_str)
            if hasattr(os, "add_dll_directory"):
                try:
                    handle = os.add_dll_directory(dll_dir_str)
                    _DLL_DIR_HANDLES.append(handle)
                    _log(f"[RTHOOK] Registered DLL dir: {dll_dir_str}")
                except Exception:
                    _log(f"[RTHOOK] Failed DLL dir register: {dll_dir_str}")


def _preload_torch() -> None:
    if sys.platform != "win32":
        return

    try:
        import torch  # noqa: F401
        os.environ["EMBEREYE_TORCH_PRELOADED"] = "1"
        _log("[RTHOOK] torch preloaded successfully")
    except Exception as exc:
        os.environ["EMBEREYE_TORCH_PRELOADED"] = "0"
        _log(f"[RTHOOK] torch preload failed: {type(exc).__name__}: {exc}")


_register_dll_dirs()
_preload_torch()
