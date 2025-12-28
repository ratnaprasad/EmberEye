# EmberEye v1.0.0-beta - Distribution Setup Guide

Complete instructions for packaging EmberEye for Windows, Linux, and macOS with automatic GPU/CPU detection.

---

## 📋 Prerequisites

### Windows (Packaging Machine)

```powershell
# 1. Install Python 3.12+ (from python.org)
# During installation: CHECK "Add Python to PATH"

# 2. Install Git for Windows
# Download from: https://git-scm.com/download/win

# 3. Install PyInstaller (for .exe generation)
pip install pyinstaller

# 4. For Linux/macOS packaging: Install WSL2 (Windows Subsystem for Linux)
wsl --install Ubuntu-22.04

# 5. For macOS .dmg files: Use macOS machine directly (or use virtual machine)
```

### System Requirements by Target

| Target   | Requirements | GPU Support |
|----------|-------------|------------|
| **Windows** | Python 3.12+, PyInstaller, 8GB+ RAM | NVIDIA CUDA, AMD ROCm, Intel oneAPI |
| **Linux (DEB)** | Python 3.12+, fpm, dpkg, 8GB+ RAM | NVIDIA CUDA, AMD ROCm, Intel oneAPI |
| **macOS** | Python 3.12+, 10GB+ RAM | Metal (Apple Silicon), NVIDIA (older Macs) |

---

## 🚀 Step 1: Clone & Setup EmberEye on Windows

```powershell
# 1. Clone repository
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye

# 2. Create Python virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. Verify installation
python -c "import embereye; print('✅ EmberEye ready')"
```

---

## 🎯 Step 2: Configure GPU/CPU Auto-Detection

### Option A: Automatic Detection (Recommended)

Create `embereye/config/device_config.py`:

```python
"""
Auto-detect and configure GPU/CPU for YOLOv8
"""

import torch
import os
from pathlib import Path

def get_device_config():
    """
    Returns optimal device configuration based on available hardware
    """
    config = {
        'device': 'cpu',
        'device_name': 'CPU (Default)',
        'gpu_available': False,
        'gpu_type': None,
        'mixed_precision': False,
        'memory_fraction': 0.8
    }
    
    try:
        # Check NVIDIA CUDA
        if torch.cuda.is_available():
            config['device'] = 0  # GPU device index
            config['device_name'] = f"NVIDIA {torch.cuda.get_device_name(0)}"
            config['gpu_available'] = True
            config['gpu_type'] = 'NVIDIA_CUDA'
            config['mixed_precision'] = True
            
            # Log GPU info
            print(f"✅ GPU Detected: {config['device_name']}")
            print(f"   Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
            
        # Check AMD ROCm
        elif os.environ.get('HIP_VISIBLE_DEVICES') or Path('/opt/rocm').exists():
            config['device'] = 'cuda'
            config['device_name'] = 'AMD GPU (ROCm)'
            config['gpu_available'] = True
            config['gpu_type'] = 'AMD_ROCM'
            config['mixed_precision'] = False
            print(f"✅ GPU Detected: {config['device_name']}")
            
        # Check Intel oneAPI
        elif os.environ.get('ONEAPI_ROOT'):
            config['device'] = 'cpu'  # Intel GPU via CPU for now
            config['device_name'] = 'Intel GPU (via CPU mode)'
            config['gpu_available'] = False  # Requires additional setup
            config['gpu_type'] = 'INTEL_ONEAPI'
            print(f"ℹ️  Intel GPU detected but using CPU mode")
            
        else:
            print("⚠️  No GPU detected - using CPU mode")
            print("   For GPU support, install:")
            print("   - NVIDIA: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
            print("   - AMD: pip install torch-directml")
            
    except Exception as e:
        print(f"⚠️  Device detection error: {e}")
        print("   Falling back to CPU mode")
    
    return config

def log_device_config(config):
    """Pretty print device configuration"""
    print("\n" + "="*50)
    print("DEVICE CONFIGURATION")
    print("="*50)
    print(f"Device: {config['device_name']}")
    print(f"GPU Available: {'✅ Yes' if config['gpu_available'] else '❌ No'}")
    print(f"Mixed Precision: {'✅ Enabled' if config['mixed_precision'] else '❌ Disabled'}")
    print(f"Memory Fraction: {config['memory_fraction']*100:.0f}%")
    print("="*50 + "\n")

# Global configuration
DEVICE_CONFIG = get_device_config()

# Update YOLOv8 settings
def configure_yolo():
    """Configure YOLOv8 with detected device"""
    from ultralytics import YOLO
    
    yolo_config = {
        'device': DEVICE_CONFIG['device'],
        'half': DEVICE_CONFIG['mixed_precision'],
        'amp': DEVICE_CONFIG['mixed_precision'],
    }
    
    return yolo_config
```

### Option B: User-Selected Device

Add to `main_window.py`:

```python
def setup_device_selection_dialog(self):
    """Allow users to select device at startup"""
    from PyQt5.QtWidgets import QComboBox, QDialog, QVBoxLayout, QLabel, QPushButton
    
    dialog = QDialog(self)
    dialog.setWindowTitle("Device Selection")
    layout = QVBoxLayout()
    
    label = QLabel("Select compute device:")
    device_combo = QComboBox()
    
    devices = ["CPU", "GPU (CUDA)", "GPU (ROCm)", "Auto-Detect"]
    device_combo.addItems(devices)
    device_combo.setCurrentText("Auto-Detect")
    
    ok_button = QPushButton("OK")
    ok_button.clicked.connect(dialog.accept)
    
    layout.addWidget(label)
    layout.addWidget(device_combo)
    layout.addWidget(ok_button)
    dialog.setLayout(layout)
    
    if dialog.exec_():
        selected = device_combo.currentText()
        self.set_device(selected)
```

---

## 📦 Step 3: Generate Windows EXE

### Option A: PyInstaller (Simple)

```powershell
# 1. Activate virtual environment
.venv\Scripts\activate

# 2. Create build spec
pyinstaller --onefile `
    --windowed `
    --name "EmberEye" `
    --icon "logo.ico" `
    --add-data "embereye/resources;embereye/resources" `
    --add-data "embereye/utils;embereye/utils" `
    --hidden-import=torch `
    --hidden-import=torchvision `
    --hidden-import=ultralytics `
    --hidden-import=cv2 `
    --collect-all=ultralytics `
    --collect-all=torch `
    main.py

# 3. Output: dist/EmberEye.exe
# File size: ~800MB-1.2GB (includes all dependencies)
```

### Option B: NSIS Installer (Professional)

Create `EmberEye_Installer.nsi`:

```nsis
; EmberEye NSIS Installer Script
!include "MUI2.nsh"

Name "EmberEye v1.0.0-beta"
OutFile "EmberEye-1.0.0-beta-Setup.exe"
InstallDir "$PROGRAMFILES\EmberEye"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File "dist\EmberEye.exe"
  File "logo.ico"
  
  ; Create Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\EmberEye"
  CreateShortcut "$SMPROGRAMS\EmberEye\EmberEye.lnk" "$INSTDIR\EmberEye.exe" "" "$INSTDIR\logo.ico"
  CreateShortcut "$SMPROGRAMS\EmberEye\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  RMDir /r "$SMPROGRAMS\EmberEye"
SectionEnd
```

Generate installer:

```powershell
# Install NSIS from: https://nsis.sourceforge.io/Download
makensis EmberEye_Installer.nsi
# Output: EmberEye-1.0.0-beta-Setup.exe (~900MB)
```

---

## 🐧 Step 4: Generate Linux DEB Package

### Option A: On Ubuntu/Debian

```bash
# 1. Clone on Linux machine
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Install PyInstaller & fpm
pip install PyInstaller
sudo apt-get install ruby ruby-dev
sudo gem install fpm

# 4. Build Linux binary
pyinstaller \
    --onefile \
    --name embereye \
    --add-data "embereye/resources:embereye/resources" \
    --add-data "embereye/utils:embereye/utils" \
    --hidden-import=torch \
    --hidden-import=ultralytics \
    --collect-all=ultralytics \
    main.py

# 5. Create .deb package
mkdir -p build/embereye/usr/local/bin
cp dist/embereye build/embereye/usr/local/bin/

fpm \
    -s dir \
    -t deb \
    -n embereye \
    -v 1.0.0~beta \
    -C build/embereye \
    --description "EmberEye - Advanced thermal object detection system" \
    --depends python3.12 \
    --depends libopencv-dev \
    --post-install install_deps.sh

# Output: embereye_1.0.0~beta_amd64.deb
```

### Option B: Using WSL from Windows

```powershell
# 1. Open WSL terminal
wsl

# 2. Inside WSL, run above Linux commands
cd /mnt/c/EmberEye  # Windows path mounted in WSL
source .venv/bin/activate
# ... continue with Linux steps above

# 3. Copy .deb back to Windows
cp *.deb /mnt/c/EmberEye/dist/
```

---

## 🍎 Step 5: Generate macOS DMG (Mac-only)

### On macOS Machine

```bash
# 1. Clone repository
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye

# 2. Setup (M1/M2/Intel support)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install PyTorch for macOS
pip install torch torchvision torchaudio

# 4. Install other dependencies
pip install -r requirements.txt

# 5. Build .app bundle
pyinstaller \
    --onefile \
    --windowed \
    --name "EmberEye" \
    --icon "logo.icns" \
    --osx-bundle-identifier "com.embereye.app" \
    --add-data "embereye/resources:embereye/resources" \
    --hidden-import=torch \
    --collect-all=ultralytics \
    main.py

# 6. Sign application (for App Notarization)
codesign --deep --force --verify --verbose --sign - dist/EmberEye.app

# 7. Create DMG
hdiutil create -volname "EmberEye" \
    -srcfolder dist/EmberEye.app \
    -ov -format UDZO \
    EmberEye-1.0.0-beta.dmg

# Output: EmberEye-1.0.0-beta.dmg (~600MB)
```

---

## 📥 Step 6: Create Installation & Distribution Package

Create `DISTRIBUTION_README.md`:

```markdown
# EmberEye v1.0.0-beta - Installation Guide

## 🖥️ Windows Installation

### Automatic (Recommended)
1. Download: `EmberEye-1.0.0-beta-Setup.exe`
2. Double-click installer
3. Follow prompts
4. App installed to: `C:\Program Files\EmberEye`

### Manual
1. Download: `EmberEye-1.0.0-beta-Portable.zip`
2. Extract anywhere
3. Double-click `EmberEye.exe`

### GPU Support
- **NVIDIA**: Automatically detected (CUDA 12.1+)
- **AMD**: Install ROCm from https://rocmdocs.amd.com/
- **CPU**: Works out-of-box (slower training)

---

## 🐧 Linux Installation

### Ubuntu/Debian
\`\`\`bash
sudo dpkg -i embereye_1.0.0~beta_amd64.deb
sudo apt-get install -f  # Install dependencies if needed
embereye
\`\`\`

### From Source
\`\`\`bash
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
\`\`\`

### GPU Support
- **NVIDIA**: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`
- **AMD**: `pip install torch-directml`
- **CPU**: Works out-of-box

---

## 🍎 macOS Installation

1. Download: `EmberEye-1.0.0-beta.dmg`
2. Double-click DMG file
3. Drag `EmberEye.app` to Applications folder
4. Open from Applications

### M1/M2 Support
- Automatically uses Metal for GPU acceleration
- Native ARM64 architecture

### Intel Macs
- Works on Intel processors
- GPU support via NVIDIA (requires separate driver)

---

## ⚙️ First Run Configuration

1. **Device Selection**: Auto-detects GPU/CPU
   - NVIDIA CUDA → Full GPU acceleration
   - AMD ROCm → GPU acceleration (ROCm mode)
   - CPU → Fallback mode (slower training)

2. **Permissions**: Grant filesystem access when prompted

3. **Initial Setup**:
   - Configure RTSP streams (if applicable)
   - Import or create class taxonomy
   - Connect PFDS devices (optional)

---

## 🚀 Getting Started

See: [GITHUB_RELEASE_NOTES.md](GITHUB_RELEASE_NOTES.md)
```

---

## 📦 Step 7: Package Distribution Bundle

```powershell
# Create distribution folder structure
mkdir EmberEye-Distribution
cd EmberEye-Distribution

mkdir Windows
mkdir Linux
mkdir macOS
mkdir Docs

# Windows
cp dist/EmberEye-1.0.0-beta-Setup.exe Windows/
cp dist/EmberEye-1.0.0-beta-Portable.zip Windows/

# Linux (from WSL)
cp embereye_1.0.0~beta_amd64.deb Linux/

# macOS (copy from Mac machine)
# scp user@mac:/path/EmberEye-1.0.0-beta.dmg macOS/

# Documentation
cp CHANGELOG.md Docs/
cp GITHUB_RELEASE_NOTES.md Docs/
cp DISTRIBUTION_README.md Docs/

# Create ZIP bundle
Compress-Archive -Path . -DestinationPath EmberEye-v1.0.0-beta-Distribution.zip
```

---

## 🔧 Team Distribution Checklist

### Pre-Distribution
- [ ] Test each installer on clean system
- [ ] Verify GPU detection on test machines
- [ ] Confirm all dependencies bundled
- [ ] Test with sample thermal images
- [ ] Document any prerequisites

### Distribution
- [ ] Create shared folder: `/distribution/EmberEye/v1.0.0-beta/`
- [ ] Upload all installers + documentation
- [ ] Send download links to team
- [ ] Create team wiki with setup guide
- [ ] Schedule training/demo session

### Post-Distribution
- [ ] Collect feedback from teams
- [ ] Monitor for common issues
- [ ] Create FAQ document
- [ ] Prepare hotfixes if needed
- [ ] Plan v1.0 stable release

---

## 🐛 Troubleshooting

### Windows
```powershell
# GPU not detected
python -c "import torch; print(torch.cuda.is_available())"

# CUDA installation
# Download: https://developer.nvidia.com/cuda-12-1-0-download-archive
# Select: Windows > x86_64 > 11 > exe

# Verify after install
nvidia-smi
```

### Linux
```bash
# GPU not detected
python -c "import torch; print(torch.cuda.is_available())"

# NVIDIA Driver
ubuntu-drivers devices
sudo ubuntu-drivers autoinstall

# AMD ROCm
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install rocm-dkms
```

### macOS
```bash
# Check Metal GPU
python -c "import torch; print(torch.backends.mps.is_available())"

# Reinstall PyTorch for macOS
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio
```

---

## 📊 Package Sizes

| Platform | File | Size |
|----------|------|------|
| Windows | Setup .exe | ~900 MB |
| Windows | Portable .zip | ~950 MB |
| Linux | .deb package | ~800 MB |
| macOS | .dmg bundle | ~600 MB |

---

## 🔐 Security Notes

- All packages include pinned dependency versions
- No external package downloads at runtime
- GPU drivers remain system responsibility
- Optional SSL verification for RTSP streams
- Audit logs in `~/.embereye/logs/`

---

## 📞 Support

- **Issues**: https://github.com/ratnaprasad/EmberEye/issues
- **Documentation**: See `/docs/` folder
- **Team Training**: Contact core team

---

**Version**: 1.0.0-beta  
**Release Date**: 2025-12-27  
**Platforms**: Windows 10+, Ubuntu 20.04+, macOS 11.0+
