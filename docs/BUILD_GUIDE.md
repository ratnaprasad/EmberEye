# EmberEye Multi-Platform Build Guide

## Overview

This guide explains how to build EmberEye executables for Windows, Linux, and macOS.

## Pre-configured Users

All builds include these three users:
- **admin** / password (Administrator)
- **ratna** / ratna (Standard user)
- **s3micro** / s3micro (Demo user)

## Quick Build

```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Run build script
python build_installer.py
```

The script will:
1. ✓ Check/install PyInstaller
2. ✓ Prepare database with all three users
3. ✓ Ensure resources (logo, config) exist
4. ✓ Create platform-specific executable

## Platform-Specific Builds

### macOS (.app bundle)

```bash
source .venv/bin/activate
python build_installer.py
```

**Output:** `dist/EmberEye.app`

**Create DMG installer:**
```bash
# Install create-dmg
brew install create-dmg

# Create DMG
create-dmg \
  --volname "EmberEye Installer" \
  --volicon "logo.png" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "EmberEye.app" 175 120 \
  --app-drop-link 425 120 \
  "EmberEye-Installer.dmg" \
  "dist/EmberEye.app"
```

### Windows (.exe)

**On Windows machine:**
```cmd
.venv\Scripts\activate
python build_installer.py
```

**Output:** `dist\EmberEye.exe`

**Create installer with Inno Setup:**
1. Download Inno Setup: https://jrsoftware.org/isdl.php
2. Create `installer.iss`:

```inno
[Setup]
AppName=EmberEye
AppVersion=1.0.0
DefaultDirName={pf}\EmberEye
DefaultGroupName=EmberEye
OutputDir=installers
OutputBaseFilename=EmberEye-Setup-Windows
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\EmberEye.exe"; DestDir: "{app}"
Source: "logo.png"; DestDir: "{app}"
Source: "README.txt"; DestDir: "{app}"

[Icons]
Name: "{group}\EmberEye"; Filename: "{app}\EmberEye.exe"
Name: "{commondesktop}\EmberEye"; Filename: "{app}\EmberEye.exe"

[Run]
Filename: "{app}\EmberEye.exe"; Description: "Launch EmberEye"; Flags: postinstall nowait skipifsilent
```

3. Compile with Inno Setup

### Linux (Ubuntu/Debian)

```bash
source .venv/bin/activate
python build_installer.py
```

**Output:** `dist/EmberEye` (executable binary)

**Create .deb package:**
```bash
# Install fpm
sudo apt-get install ruby ruby-dev rubygems build-essential
sudo gem install fpm

# Create package
fpm -s dir -t deb -n embereye -v 1.0.0 \
  --description "EmberEye Fire Detection System" \
  --url "https://s3micro.com" \
  --maintainer "S3 Micro <support@s3micro.com>" \
  --after-install post-install.sh \
  dist/EmberEye=/usr/local/bin/embereye \
  logo.png=/usr/share/embereye/logo.png \
  README.txt=/usr/share/embereye/README.txt
```

**Create .rpm package (for RedHat/CentOS):**
```bash
fpm -s dir -t rpm -n embereye -v 1.0.0 \
  --description "EmberEye Fire Detection System" \
  --url "https://s3micro.com" \
  --maintainer "S3 Micro <support@s3micro.com>" \
  dist/EmberEye=/usr/local/bin/embereye \
  logo.png=/usr/share/embereye/logo.png \
  README.txt=/usr/share/embereye/README.txt
```

## Build Output

After successful build:
```
dist/
├── EmberEye.app       (macOS)
├── EmberEye.exe       (Windows)
├── EmberEye           (Linux)
└── README.txt         (User documentation)
```

## Testing Builds

### macOS
```bash
open dist/EmberEye.app
```

### Windows
```cmd
dist\EmberEye.exe
```

### Linux
```bash
chmod +x dist/EmberEye
./dist/EmberEye
```

## Troubleshooting

### "Permission Denied" (macOS/Linux)
```bash
chmod +x dist/EmberEye
```

### "Cannot be opened because developer cannot be verified" (macOS)
```bash
xattr -cr dist/EmberEye.app
```
Or: System Preferences → Security & Privacy → "Open Anyway"

### Missing dependencies
```bash
pip install -r requirements.txt
```

### Database issues
Delete `users.db` and rebuild - script will recreate with all users

## Distribution Checklist

- [ ] Build on target platform
- [ ] Test all three user logins (admin, ratna, s3micro)
- [ ] Test camera stream connection
- [ ] Test sensor data display
- [ ] Create installer package (.dmg, .exe, .deb)
- [ ] Include README.txt
- [ ] Test installation on clean system

## Cross-Platform Notes

### Building for other platforms
- **macOS→Windows:** Use Wine or Windows VM
- **Windows→macOS:** Use macOS VM or remote build
- **Linux→Windows:** Use Wine or Windows VM

### Universal Binary (macOS Apple Silicon + Intel)
```bash
# Install universal2 packages
pip install --upgrade --force-reinstall \
  --platform macosx_10_9_universal2 \
  --target .venv/lib/python3.x/site-packages \
  PyQt5 numpy opencv-python

# Build
python build_installer.py
```

## File Sizes (Approximate)

- macOS .app: ~150-200 MB
- Windows .exe: ~120-150 MB  
- Linux binary: ~120-150 MB

## Support

For build issues, check:
1. Python version: 3.8+
2. All dependencies installed: `pip install -r requirements.txt`
3. PyInstaller version: 6.0+
4. Platform-specific tools (Xcode/Visual Studio/gcc)
