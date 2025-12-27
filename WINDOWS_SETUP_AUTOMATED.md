# EmberEye v1.0.0-beta - Automated Windows Setup Guide

**Complete automated setup with error logging and troubleshooting**

---

## 🚀 Quick Start (1 Step!)

### Option A: Default Installation (Recommended)

1. **Download the setup script** from: [GitHub EmberEye Repository](https://github.com/ratnaprasad/EmberEye)
2. **Double-click**: `setup_windows.bat`
3. Wait 10-15 minutes for full installation
4. Done! 🎉

### Option B: Custom Installation Path

```powershell
# Open PowerShell as Administrator and run:
powershell -NoProfile -ExecutionPolicy Bypass -Command "& 'C:\path\to\setup_windows.ps1' -InstallPath 'D:\MyApps\EmberEye'"
```

---

## 📋 What the Script Does

### Automatically Checks & Installs:
- ✅ Python 3.12+ (checks version, upgrades if needed)
- ✅ Git (checks version, upgrade if needed)
- ✅ PyInstaller (for building .exe)
- ✅ All Python dependencies (from requirements.txt)
- ✅ GPU/CPU detection configuration

### Setup Steps:
1. **Prerequisites Check** - Verifies Python 3.12+ and Git
2. **Repository Clone** - Downloads EmberEye from GitHub
3. **Virtual Environment** - Creates isolated Python environment
4. **Dependencies Install** - Installs all required packages
5. **Build Tools** - Installs PyInstaller for .exe generation
6. **Verification Tests** - Runs smoke tests
7. **Desktop Shortcuts** - Creates convenient launch shortcuts

---

## 🎯 Execution Modes

### Mode 1: Run Setup Script Directly (Simplest)

```batch
# Just double-click this file:
setup_windows.bat

# It will install to: C:\EmberEye
```

### Mode 2: Custom Installation Path

```batch
# Right-click Command Prompt, "Run as Administrator"
setup_windows.bat D:\CustomPath\EmberEye

# Or using PowerShell:
powershell -NoProfile -ExecutionPolicy Bypass -Command "& 'setup_windows.ps1' -InstallPath 'D:\CustomPath'"
```

### Mode 3: Force Reinstall

```powershell
# If repository already exists, force re-clone:
powershell -NoProfile -ExecutionPolicy Bypass -Command "& 'setup_windows.ps1' -Force"
```

---

## 📊 Logging & Error Tracking

The script creates three log files in your installation directory:

### Log Files Created:

1. **`setup_log_YYYY-MM-DD_HH-MM-SS.txt`** (Main Log)
   - All events and steps
   - Version checks
   - Installation progress

2. **`setup_errors_YYYY-MM-DD_HH-MM-SS.txt`** (Errors Only)
   - Only errors encountered
   - Error messages and codes
   - Easy for troubleshooting

3. **`setup_warnings_YYYY-MM-DD_HH-MM-SS.txt`** (Warnings Only)
   - Non-critical warnings
   - Version mismatches (if any)
   - Optional installations

### 📤 Share Logs with Support:

If setup fails, share these files:
```
C:\EmberEye\setup_errors_*.txt
C:\EmberEye\setup_log_*.txt
```

---

## ⚙️ Version Requirements

| Component | Minimum | Recommended |
|-----------|---------|------------|
| Python | 3.12.0 | 3.12.2+ |
| Git | 2.40+ | 2.42+ |
| Windows | 10 | 10/11 |

---

## ✅ Successful Installation Indicators

### You'll see:
```
╔════════════════════════════════════════════════════════════════╗
║           ✅ SETUP COMPLETED SUCCESSFULLY! ✅                 ║
╚════════════════════════════════════════════════════════════════╝

📍 Installation Location: C:\EmberEye
📊 Log Files:
   - Main Log: C:\EmberEye\setup_log_2025-12-27_10-30-45.txt
   - Errors:   C:\EmberEye\setup_errors_2025-12-27_10-30-45.txt
   - Warnings: C:\EmberEye\setup_warnings_2025-12-27_10-30-45.txt

🚀 Next Steps:
   1. Launch EmberEye from desktop shortcut, or
   2. Run: cd C:\EmberEye && .\.venv\Scripts\activate && python main.py
   3. To build .exe: Run build_windows.bat
```

### Desktop Shortcuts Created:
- `EmberEye.lnk` - Direct launch app
- `EmberEye (Folder).lnk` - Open repository folder

---

## 🐛 Troubleshooting

### Problem: "Python not found in PATH"

**Solution:**
1. Download Python 3.12 from: https://www.python.org/downloads/
2. **IMPORTANT**: During installation, CHECK "Add Python to PATH"
3. Restart Command Prompt/PowerShell
4. Run setup script again

### Problem: "Git not found in PATH"

**Solution:**
1. Download Git from: https://git-scm.com/download/win
2. Accept all default settings
3. Restart Command Prompt/PowerShell
4. Run setup script again

### Problem: "Virtual environment creation failed"

**Solution:**
1. Check: `python -m venv --help`
2. If error, reinstall Python with "venv" module
3. Try running setup script again

### Problem: "Dependency installation failed"

**Solution:**
1. Check internet connection
2. Look at error log: `setup_errors_*.txt`
3. Common fixes:
   ```powershell
   cd C:\EmberEye
   .\.venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Problem: "GPU not detected"

**This is OK!** The app works fine on CPU.

If you want GPU support:
- **NVIDIA**: Install CUDA 12.1 from: https://developer.nvidia.com/cuda-12-1-0-download-archive
- **AMD**: Install ROCm from: https://rocmdocs.amd.com/
- Then reinstall PyTorch:
  ```powershell
  cd C:\EmberEye
  .\.venv\Scripts\activate
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  ```

---

## 📦 After Setup - What to Do

### 1. **Test the Installation**

```powershell
# Open Command Prompt and run:
cd C:\EmberEye
.\.venv\Scripts\activate
python main.py

# App should launch with no errors
```

### 2. **Build Windows .exe** (for distribution)

```batch
# Double-click:
C:\EmberEye\build_windows.bat

# Output: C:\EmberEye\dist\EmberEye.exe (~1GB)
```

### 3. **Create Professional Installer** (optional)

```batch
# Install NSIS first: https://nsis.sourceforge.io/Download
# Then double-click:
C:\EmberEye\build_installer.bat

# Output: C:\EmberEye\dist\EmberEye-Setup.exe (~900MB)
```

---

## 📊 Installation Directory Structure

After successful setup:

```
C:\EmberEye\
├── EmberEye/                    ← Source code
│   ├── main.py
│   ├── build_windows.bat
│   ├── build_installer.bat
│   ├── embereye/
│   ├── .venv/                   ← Virtual environment
│   ├── dist/                    ← Built executables (after build)
│   └── requirements.txt
│
├── setup_log_*.txt              ← Setup log (complete)
├── setup_errors_*.txt           ← Error log (if any)
└── setup_warnings_*.txt         ← Warning log (if any)
```

---

## 🔧 Manual Setup (If Automated Fails)

If the automated script doesn't work, manual steps:

```powershell
# 1. Install Python 3.12 manually from https://www.python.org/downloads/
# 2. Install Git manually from https://git-scm.com/download/win
# 3. Then run these commands:

cd C:\EmberEye
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install PyInstaller
python main.py
```

---

## 💡 Tips & Tricks

### Change Installation Path

```batch
setup_windows.bat D:\Apps\EmberEye
```

### Reinstall (Force Mode)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& 'setup_windows.ps1' -Force"
```

### Check Python Version

```powershell
python --version
```

### Check Git Version

```powershell
git --version
```

### Activate Virtual Environment Manually

```powershell
cd C:\EmberEye
.\.venv\Scripts\activate
```

### Deactivate Virtual Environment

```powershell
deactivate
```

---

## 📞 Support & Issues

### If Setup Fails:

1. **Check Error Log**: `setup_errors_*.txt`
2. **Share These Files**:
   - `setup_log_*.txt`
   - `setup_errors_*.txt`
   - `setup_warnings_*.txt`
3. **Open GitHub Issue**: https://github.com/ratnaprasad/EmberEye/issues

### Common Issues:
- Python/Git not in PATH → Reinstall with PATH enabled
- Network timeout → Try again (download may be slow)
- Antivirus blocking → Temporarily disable or whitelist Python
- Disk space → Need ~5GB free for full installation

---

## ✨ What Happens Next

After successful setup:

1. **EmberEye is ready to use** ✅
2. **GPU/CPU auto-detected** ✅
3. **Desktop shortcuts created** ✅
4. **Can build .exe for distribution** ✅
5. **All logs available for troubleshooting** ✅

---

## 🎯 Success Checklist

After setup completes, verify:

- [ ] No errors in setup script output
- [ ] Desktop shortcuts created
- [ ] Log files exist and show success
- [ ] Can launch EmberEye from shortcut
- [ ] App displays device info (GPU or CPU)
- [ ] All tabs visible (Training, VideoWall, etc.)

---

**Version**: 1.0.0-beta  
**Created**: 2025-12-27  
**Fully Automated**: ✅ Yes  
**Error Logging**: ✅ Yes  
**GPU Detection**: ✅ Automatic
