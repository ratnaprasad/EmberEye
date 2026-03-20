# EmberEye Studio - Known Bugs & Issues

**Document Purpose:** Track all known bugs, issues, and required fixes for the EmberEye Studio application.

**Date Created:** February 20, 2026  
**Last Updated:** February 20, 2026  
**Status:** Active Bug Tracking

---

## 🐛 CRITICAL BUGS

### ❌ BUG #1: GPU Not Detected in Packaged EXE

**Status:** 🔴 OPEN - Requires Investigation  
**Priority:** 🔥 CRITICAL - Affects performance on all GPU-capable machines  
**Affects:** EmberEye Studio (embereye-studio.exe) - Packaged/Frozen application only  
**Reported:** February 20, 2026  

#### Problem Description
When running the packaged EmberEye Studio executable (.exe), GPU is not being detected even on machines with CUDA-capable GPUs. The application falls back to CPU mode, significantly impacting training and inference performance.

#### Symptoms
- ✅ **Python mode** (running via `python main.py`): GPU detected correctly ✓
- ❌ **EXE mode** (running `EmberEyeStudio.exe`): Always shows "CPU mode: no GPU detected" ✗
- UI status bar shows: "Device: cpu" instead of "Device: gpu"
- Startup log (when created): `[timestamp] CPU mode: no GPU detected`
- Training and inference run on CPU only (very slow)

#### Environment Details
- **OS:** Windows 11
- **GPU:** NVIDIA GeForce RTX 5070 (Compute Capability: sm_120, 11.9GB VRAM)
- **PyTorch:** 2.10.0+cu128
- **CUDA:** 12.8
- **PyInstaller:** 6.19.0
- **Python:** 3.12.10

#### What's Been Tried
1. ✅ **Added PyQt5 to frozen app** - Was missing initially, now bundled correctly in `_internal/PyQt5/`
2. ✅ **Updated torch DLL path detection** - Fixed logic for frozen apps (sys._MEIPASS points to _internal)
3. ✅ **Verified CUDA DLLs are packaged** - Confirmed presence of c10_cuda.dll, cublas64_12.dll, cudnn64_9.dll, etc.
4. ✅ **Confirmed torch libraries exist** - Located at: `_internal\torch\lib\` with all CUDA DLLs
5. ✅ **Fixed path candidates** - Updated main.py and embereye_base/core/training_pipeline.py to use correct frozen app paths
6. ❌ **Still showing CPU mode** - Issue persists in frozen EXE

#### Root Cause (Suspected)
The torch DLL path setup in `main.py` and `forgelab/training_pipeline.py` runs BEFORE torch is loaded, but the PATH environment variable or DLL directory may not be properly recognized by torch at runtime in the frozen app. Possible issues:
- DLLs not in PATH when torch.cuda module initializes
- os.add_dll_directory() called too late or not effective in frozen context
- CUDA runtime environment variables missing
- PyInstaller bootstrap interfering with DLL loading

#### Potential Solutions

**Option 1: Force DLL path with CUDA environment variables**
```python
# In main.py, BEFORE "import torch"
if getattr(sys, "frozen", False):
    meipass = Path(getattr(sys, "_MEIPASS"))
    torch_lib = meipass / "torch" / "lib"
    if torch_lib.exists():
        # Force PATH update
        os.add_dll_directory(str(torch_lib))
        os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
        
        # Add CUDA-specific environment variables
        os.environ["CUDA_PATH"] = str(torch_lib.parent)
        os.environ["CUDA_PATH_V12_8"] = str(torch_lib.parent)
        os.environ["TORCH_CUDA_ARCH_LIST"] = "sm_120"  # Match RTX 5070 capability
```

**Option 2: Manually preload CUDA DLLs using ctypes**
```python
if getattr(sys, "frozen", False):
    import ctypes
    meipass = Path(getattr(sys, "_MEIPASS"))
    torch_lib = meipass / "torch" / "lib"
    
    # Preload critical CUDA DLLs in dependency order
    critical_dlls = [
        "cudart64_12.dll",      # CUDA runtime (load first)
        "cublas64_12.dll",      # CUDA BLAS
        "cublasLt64_12.dll",    # CUDA BLAS Light
        "cudnn64_9.dll",        # cuDNN
        "c10_cuda.dll",         # PyTorch CUDA C10
    ]
    for dll in critical_dlls:
        dll_path = torch_lib / dll
        if dll_path.exists():
            try:
                ctypes.CDLL(str(dll_path))
                print(f"✓ Preloaded {dll}")
            except Exception as e:
                print(f"✗ Failed to preload {dll}: {e}")
```

**Option 3: Add debug logging to diagnose DLL loading**
```python
# In embereye_base/core/training_pipeline.py, get_available_devices()
# Add debug logging BEFORE torch.cuda.is_available() check
if getattr(sys, "frozen", False):
    import sys
    print(f"DEBUG: Frozen app detected")
    print(f"DEBUG: sys._MEIPASS = {getattr(sys, '_MEIPASS', 'NOT SET')}")
    print(f"DEBUG: CUDA_VISIBLE_DEVICES = {os.environ.get('CUDA_VISIBLE_DEVICES', 'NOT SET')}")
    print(f"DEBUG: CUDA_PATH = {os.environ.get('CUDA_PATH', 'NOT SET')}")
    print(f"DEBUG: PATH = {os.environ.get('PATH', '')[:200]}...")
    
    torch_lib_path = Path(sys._MEIPASS) / "torch" / "lib"
    print(f"DEBUG: torch/lib exists = {torch_lib_path.exists()}")
    if torch_lib_path.exists():
        print(f"DEBUG: torch/lib path = {torch_lib_path}")
        print(f"DEBUG: DLLs in torch/lib = {list(torch_lib_path.glob('*.dll'))[:5]}")
```

**Option 4: Verify torch CUDA build in frozen app**
```python
# Add to main.py startup (after torch import)
import torch
print(f"=== Torch Debug Info ===")
print(f"Torch version: {torch.__version__}")
print(f"CUDA compiled: {torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A'}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU count: {torch.cuda.device_count()}")
    print(f"GPU name: {torch.cuda.get_device_name(0)}")
else:
    print(f"CUDA not available - reason unknown")
print(f"=======================")
```

**Option 5: PyInstaller spec file - Add runtime hook**
Create a custom runtime hook to set up CUDA environment before torch loads:
```python
# File: embereye-studio/hooks/rthook_cuda_setup.py
import os
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    base_path = Path(sys._MEIPASS)
    torch_lib = base_path / "torch" / "lib"
    
    if torch_lib.exists():
        # Set up PATH
        torch_lib_str = str(torch_lib)
        if torch_lib_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = torch_lib_str + os.pathsep + os.environ.get("PATH", "")
        
        # Add DLL directory
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(torch_lib_str)
        
        # Set CUDA paths
        os.environ["CUDA_PATH"] = str(torch_lib.parent)
        os.environ["CUDA_HOME"] = str(torch_lib.parent)
```

Then add to `EmberEyeStudio.spec`:
```python
a = Analysis(
    ['main.py'],
    pathex=['.'],
    runtime_hooks=['hooks/rthook_cuda_setup.py'],  # Add this
    # ... rest of config
)
```

#### Files to Modify
- **embereye-studio/main.py** (lines 13-50) - DLL path setup before torch import
- **embereye-studio/forgelab/training_pipeline.py** (lines 19-55) - DLL path setup
- **embereye-studio/EmberEyeStudio.spec** - PyInstaller configuration
- **(Optional) embereye-studio/hooks/rthook_cuda_setup.py** - New runtime hook file

#### Success Criteria
- ✅ Launch `EmberEyeStudio.exe` from dist folder
- ✅ UI status bar shows: "Device: gpu" (not "Device: cpu")
- ✅ Startup log shows: `[timestamp] GPU ready: NVIDIA GeForce RTX 5070`
- ✅ torch.cuda.is_available() returns True in frozen app
- ✅ Training and inference use GPU acceleration
- ✅ No performance degradation compared to Python mode

#### Next Investigation Steps
1. **Add debug logging (Option 3)** - Understand what's happening at runtime
2. **Try runtime hook (Option 5)** - Ensure CUDA setup happens in PyInstaller bootstrap phase
3. **Test manual DLL preload (Option 2)** - Force Windows to load CUDA DLLs before torch
4. **Verify CUDA env vars (Option 1)** - Set all possible CUDA paths
5. **Test on clean machine** - Rule out local environment issues
6. **Compare with working frozen PyTorch apps** - Research successful PyInstaller+CUDA examples

#### References
- PyInstaller CUDA issues: https://github.com/pyinstaller/pyinstaller/issues?q=cuda
- PyTorch frozen app discussions: https://discuss.pytorch.org/search?q=pyinstaller
- Related GitHub issues: (add links as found)

---

## 🟡 HIGH PRIORITY BUGS

(No bugs logged yet)

---

## 🟢 MEDIUM PRIORITY BUGS

(No bugs logged yet)

---

## 🔵 LOW PRIORITY BUGS

(No bugs logged yet)

---

## ✅ RESOLVED BUGS

### ✅ RESOLVED #1: PyQt5 Not Bundled in Frozen App
**Resolved:** February 20, 2026  
**Issue:** ModuleNotFoundError: No module named 'PyQt5' when running EXE  
**Solution:** Added PyQt5 as explicit datas entry in EmberEyeStudio.spec  
**Files Changed:** EmberEyeStudio.spec  

---

## 📊 Bug Statistics

- **Total Open:** 1
- **Critical:** 1
- **High Priority:** 0
- **Medium Priority:** 0
- **Low Priority:** 0
- **Resolved:** 1

---

## 📝 How to Report a Bug

When adding a new bug to this document:

1. **Assign a number** - Use next sequential number (e.g., BUG #2, BUG #3)
2. **Set priority** - Critical 🔥, High 🟡, Medium 🟢, Low 🔵
3. **Include details:**
   - Clear problem description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, versions, hardware)
   - Error messages or logs
   - What's been tried
4. **Suggest solutions** - Potential fixes or workarounds
5. **List affected files** - Where code changes are needed
6. **Define success criteria** - How to verify the fix works

---

**Document Owner:** EmberEye Studio Development Team  
**Review Frequency:** Weekly during active development  
**Last Review:** February 20, 2026
