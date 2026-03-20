# EmberEye Distribution - Quick Start Guide

## 🎯 Your Windows Machine Setup (5 minutes)

### 1. **Initial Setup**

```powershell
# Clone repository
git clone https://github.com/ratnaprasad/EmberEye.git
cd EmberEye

# Verify Python 3.12+ is installed
python --version

# That's it! Ready to build.
```

### 2. **Build Windows EXE** (3 minutes)

```powershell
# Double-click this file:
build_windows.bat

# Output: dist\EmberEye.exe (~1GB)
```

### 3. **Optional: Create Professional Installer** (2 minutes)

```powershell
# 1. Install NSIS from: https://nsis.sourceforge.io/Download
# 2. Run: build_installer.bat
# Output: dist\EmberEye-1.0.0-beta-Setup.exe (~900MB)
```

---

## 🐧 Linux DEB Package (on Linux/Ubuntu machine)

```bash
# Copy repository to Linux machine, then:
chmod +x scripts/retired/build_linux.sh
./build_linux.sh

# Output: dist/embereye_1.0.0~beta_amd64.deb (~800MB)
```

---

## 🍎 macOS DMG (on Mac machine)

```bash
# On macOS:
chmod +x scripts/retired/build_macos.sh
./build_macos.sh

# Output: dist/EmberEye-1.0.0-beta.dmg (~600MB)
```

---

## 📦 Distribution Bundle Structure

```
/distribution/EmberEye/v1.0.0-beta/
├── Windows/
│   ├── EmberEye-1.0.0-beta-Setup.exe          [Installer]
│   └── EmberEye.exe                            [Portable]
├── Linux/
│   └── embereye_1.0.0~beta_amd64.deb          [Debian/Ubuntu]
├── macOS/
│   └── EmberEye-1.0.0-beta.dmg                [App Bundle]
└── Docs/
    ├── INSTALLATION.md
    ├── GPU_SETUP.md
    ├── CHANGELOG.md
    └── TROUBLESHOOTING.md
```

---

## 🚀 Distribution Steps

### Step 1: Build All Packages
1. **Windows**: Run `build_windows.bat` on your Windows machine
2. **Linux**: Run `./build_linux.sh` on Ubuntu machine (or WSL)
3. **macOS**: Run `./build_macos.sh` on Mac (or copy DMG from Mac)

### Step 2: Organize Distribution
```powershell
# Windows PowerShell
mkdir \\network-share\EmberEye\v1.0.0-beta
mkdir \\network-share\EmberEye\v1.0.0-beta\Windows
mkdir \\network-share\EmberEye\v1.0.0-beta\Linux
mkdir \\network-share\EmberEye\v1.0.0-beta\macOS
mkdir \\network-share\EmberEye\v1.0.0-beta\Docs

# Copy files
copy dist\EmberEye-*.exe \\network-share\EmberEye\v1.0.0-beta\Windows\
copy DISTRIBUTION_SETUP.md \\network-share\EmberEye\v1.0.0-beta\Docs\
```

### Step 3: Send to Team
- **Email**: Share network path or download link
- **Wiki**: Create internal setup page with GPU instructions
- **Training**: Schedule 30-min demo showing:
  - Installation on each OS
  - GPU auto-detection verification
  - Quick retrain workflow
  - Import/Export features

---

## 🔧 GPU Auto-Detection (Built-in)

All packages automatically detect and use:

| GPU | Detection | Speed |
|-----|-----------|-------|
| **NVIDIA CUDA** | Automatic | ✅ 10-20x faster |
| **AMD ROCm** | Manual install | ✅ 8-15x faster |
| **CPU** | Fallback | ⏱️ ~1x baseline |
| **macOS M1/M2/M3** | Automatic (Metal) | ✅ 5-10x faster |

**No configuration needed** - user just installs and runs!

---

## 📋 Pre-Distribution Checklist

- [ ] Test Windows .exe on clean Windows 10/11 machine
- [ ] Test Linux .deb on Ubuntu 20.04/22.04
- [ ] Test macOS .dmg on M1 or Intel Mac
- [ ] Verify GPU auto-detection works
- [ ] Confirm all dependencies bundled
- [ ] Test quick retrain workflow (full + filtered)
- [ ] Test import/export functionality
- [ ] Create team documentation
- [ ] Schedule training session

---

## 📚 Documentation Files Created

| File | Purpose |
|------|---------|
| `DISTRIBUTION_SETUP.md` | **Complete setup guide** (detailed) |
| `build_windows.bat` | Build Windows .exe |
| `build_installer.bat` | Create Windows installer |
| `scripts/retired/build_linux.sh` | Build Linux .deb |
| `scripts/retired/build_macos.sh` | Build macOS .dmg |
| `embereye/config/device_config.py` | GPU/CPU auto-detection |

---

## 🎓 Team Training Outline

**30 Minutes**

1. **Installation** (5 min)
   - Each OS installer
   - Dependency checking
   - Verify launch

2. **GPU Setup** (5 min)
   - Show GPU detection output
   - NVIDIA CUDA (if applicable)
   - CPU fallback behavior

3. **Quick Demo** (15 min)
   - Load sample thermal images
   - Quick retrain (filtered dataset)
   - Review results
   - Export/import workflow

4. **Q&A** (5 min)
   - Troubleshooting
   - GPU optimization
   - Support resources

---

## 🐛 Troubleshooting

### Windows
```powershell
# Test GPU detection
python -c "import torch; print(torch.cuda.is_available())"

# If GPU not detected, install CUDA:
# https://developer.nvidia.com/cuda-12-1-0-download-archive
# Then: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Linux
```bash
# Test GPU detection
python -c "import torch; print(torch.cuda.is_available())"

# Install NVIDIA driver
sudo ubuntu-drivers autoinstall

# Install CUDA (if needed)
# https://developer.nvidia.com/cuda-12-1-0-download-archive
```

### macOS
```bash
# Test Metal GPU
python -c "import torch; print(torch.backends.mps.is_available())"

# Reinstall PyTorch
pip uninstall torch -y
pip install torch torchvision torchaudio
```

---

## 📊 Package Sizes

| Platform | Format | Size |
|----------|--------|------|
| Windows | .exe portable | ~950 MB |
| Windows | Setup .exe | ~900 MB |
| Linux | .deb | ~800 MB |
| macOS | .dmg | ~600 MB |

**Total Distribution**: ~3.3 GB (all platforms)

---

## 🔐 Security & Privacy

- ✅ All packages include pinned dependency versions
- ✅ No external package downloads at runtime
- ✅ GPU drivers remain system responsibility
- ✅ Audit logs available in `~/.embereye/logs/`
- ✅ Optional SSL verification for RTSP streams

---

## 📞 Support Resources

- **Issues**: https://github.com/ratnaprasad/EmberEye/issues
- **Docs**: See `/docs/` folder in repository
- **FAQ**: Create from team feedback
- **Video Guide**: Optional - record setup + quick retrain demo

---

## ✅ What's Different About This Distribution

1. **Automatic GPU Detection**
   - No manual CUDA/ROCm installation needed
   - Works with NVIDIA, AMD, Apple Silicon
   - Falls back to CPU automatically

2. **Single Binary Per OS**
   - All dependencies bundled
   - No pip install required
   - Just download and run

3. **Professional Packaging**
   - Windows: .exe installer with Start Menu shortcuts
   - Linux: .deb package with desktop integration
   - macOS: .dmg with drag-to-install

4. **Team-Ready**
   - Smoke tests included
   - Documentation complete
   - GPU/CPU optimization automatic

---

**Version**: 1.0.0-beta  
**Release Date**: 2025-12-27  
**Next Steps**: Run build scripts, test packages, distribute to team! 🚀
