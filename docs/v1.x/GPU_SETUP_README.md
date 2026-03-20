# EmberEye GPU Setup Guide

## Problem
By default, `pip install` installs the **CPU-only** version of PyTorch, even if you have an NVIDIA GPU. This means EmberEye Studio will not use GPU acceleration for training.

## System Requirements for GPU Support
- **NVIDIA GPU** with CUDA Compute Capability 3.7 or higher
- **NVIDIA Drivers** version 450.80.02 or newer (Windows/Linux)
- **CUDA 11.8 or 12.x** compatible GPU
- **Windows 10/11**, **Linux**, or **macOS** (macOS uses MPS instead of CUDA)

## Quick Fix - Install PyTorch with CUDA

### Option 1: Run the automated script (Windows)
```batch
scripts/windows/install_pytorch_cuda.bat
```
Or directly in PowerShell:
```powershell
.\scripts\windows\install_pytorch_cuda.ps1
```

### Option 2: Manual installation
```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Uninstall CPU-only version
pip uninstall torch torchvision torchaudio -y

# Install CUDA version (for CUDA 12.4)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Or for CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Verify GPU is detected
```powershell
.\.venv\Scripts\Activate.ps1
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

Expected output:
```
CUDA available: True
GPU: NVIDIA GeForce RTX 5070
```

## For Building Executable (.exe)

### Important: Install CUDA PyTorch BEFORE building
When you build an `.exe` with PyInstaller, it bundles the packages that are **currently installed** in your environment.

**If you build with CPU-only PyTorch → .exe will only support CPU**
**If you build with CUDA PyTorch → .exe will support GPU**

### Steps to build GPU-enabled executable:

1. **First, install CUDA PyTorch** (using steps above)
2. **Verify GPU detection works**
3. **Then build the executable:**
   ```batch
   scripts/windows/build_windows.bat
   ```
   Or:
   ```powershell
   pyinstaller embereye-studio.spec
   ```

### Testing the executable:
The built `.exe` will check for GPU at runtime using the bundled PyTorch. If:
- **GPU found** → Uses GPU for training
- **No GPU found** → Falls back to CPU automatically

## Permanent Solution in requirements.txt

The `requirements.txt` has been left as CPU-only by default for maximum compatibility. To permanently use GPU:

### Option A: Use requirements/requirements-gpu.txt
```powershell
pip install -r requirements/requirements-gpu.txt
```

### Option B: Modify setup_windows.ps1
Edit line ~391 in `scripts/windows/setup_windows.ps1`:
```powershell
# Before (CPU-only)
& pip install -r requirements.txt

# After (GPU-enabled)
& pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
& pip install -r requirements.txt
```

## Why This Happens
1. **ultralytics** (YOLO) depends on PyTorch
2. When you run `pip install ultralytics`, pip automatically installs PyTorch as a dependency
3. **By default, pip installs the CPU version from PyPI**
4. The CUDA version must be explicitly requested from PyTorch's index

## Troubleshooting

### GPU still shows as CPU after installation
1. Check NVIDIA drivers:
   ```batch
   nvidia-smi
   ```
2. Restart EmberEye Studio after installation
3. Check status bar in Studio - should show "Device: 0" or "Device: gpu"

### RTX 5070 / RTX 50 series not supported (sm_120 error)
**Problem:** Your GPU is too new for current PyTorch release.

```
UserWarning: NVIDIA GeForce RTX 5070 with CUDA capability sm_120 is not compatible
The current PyTorch install supports CUDA capabilities ... sm_90.
```

**Why:** RTX 50 series (Blackwell) has compute capability 12.0, but PyTorch 2.10.0 only supports up to 9.0.

**Solutions:**

#### Option 1: Try PyTorch with CUDA 12.8+ (required for sm_120)
```batch
.\scripts/windows/install_pytorch_cuda128.bat
```
Or manually:
```powershell
.\.venv\Scripts\Activate.ps1
pip uninstall torch torchvision torchaudio -y
# Try CUDA 12.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
# If cu128 not available, falls back to cu126, cu125, or cu124
```

**Note:** RTX 5070 (Blackwell/sm_120) requires PyTorch binaries compiled with CUDA 12.8+. These may not be available yet.

#### Option 1B: Try PyTorch Nightly (may have newer GPU support)
```batch
.\scripts/windows/install_pytorch_nightly.bat
```

**Note:** Nightly builds are experimental and may be unstable.

#### Option 2: Use CPU training (automatic)
EmberEye Studio automatically falls back to CPU when GPU is unsupported. Training will work but be slower.

#### Option 3: Wait for official support
Check PyTorch release notes: https://pytorch.org/get-started/locally/

Monitor for PyTorch 2.11+ which should add sm_120 support.

#### When will PyTorch support RTX 50 series?
- RTX 50 series launched in early 2026
- PyTorch typically adds support within 2-3 months of new GPU release
- Check https://github.com/pytorch/pytorch/issues for updates
- Nightly builds may get support earlier

### "No module named 'torch'"
Your virtual environment is not activated. Run:
```powershell
.\.venv\Scripts\Activate.ps1
```

### CUDA version mismatch
Your GPU driver supports a specific CUDA version. To check:
```batch
nvidia-smi
```
Look for "CUDA Version: X.X" in the output. Use the appropriate PyTorch index URL:
- CUDA 11.8: `--index-url https://download.pytorch.org/whl/cu118`
- CUDA 12.1: `--index-url https://download.pytorch.org/whl/cu121`
- CUDA 12.4: `--index-url https://download.pytorch.org/whl/cu124`

Note: Newer drivers support older CUDA versions (backward compatible).

## Status Bar Indicator
EmberEye Studio now shows the detected device in the status bar:
- **Device: 0** → Using GPU (first GPU)
- **Device: cpu** → Using CPU only
- **Device: mps** → Using Apple Metal (macOS)

This is displayed immediately when the app launches.

## For Deployment
When distributing EmberEye to end users:
1. **Build two versions**: one with CPU, one with GPU
2. **Or**: Build with GPU and let auto-fallback handle CPU-only systems
3. **Include**: Instructions to run `scripts/windows/install_pytorch_cuda.bat` if GPU is not detected

## Additional Resources
- PyTorch Installation Guide: https://pytorch.org/get-started/locally/
- CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
- NVIDIA Drivers: https://www.nvidia.com/download/index.aspx
