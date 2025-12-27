#!/bin/bash
#!/usr/bin/env zsh
set -euo pipefail

# Create a ZIP bundle of the project for Windows build
# Output: EmberEye-windows-bundle.zip at project root

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
BUNDLE_NAME="EmberEye-windows-bundle"
ZIP_FILE="$ROOT_DIR/${BUNDLE_NAME}.zip"

echo "[INFO] Preparing bundle structure..."

# Ensure windows bundle files exist
if [ ! -f "$ROOT_DIR/windows_bundle/setup_windows_complete.bat" ]; then
    echo "[ERROR] Missing windows_bundle/setup_windows_complete.bat"
    exit 1
fi
if [ ! -f "$ROOT_DIR/windows_bundle/README_WINDOWS.md" ]; then
    echo "[ERROR] Missing windows_bundle/README_WINDOWS.md"
    exit 1
fi

# Create temporary staging directory
STAGE_DIR=$(mktemp -d)
trap 'rm -rf "$STAGE_DIR"' EXIT

echo "[INFO] Staging files into $STAGE_DIR"

# Copy project files (exclude venv, build, dist, __pycache__)
rsync -av --exclude ".venv" --exclude "build" --exclude "dist" --exclude "__pycache__" --exclude ".DS_Store" --exclude ".git" "$ROOT_DIR/" "$STAGE_DIR/EmberEye/"

# Ensure required runtime files exist
mkdir -p "$STAGE_DIR/EmberEye/logs"
if [ ! -f "$STAGE_DIR/EmberEye/stream_config.json" ]; then
    echo '{"tcp_port": 9001}' > "$STAGE_DIR/EmberEye/stream_config.json"
fi
if [ ! -f "$STAGE_DIR/EmberEye/ip_loc_map.db" ] && [ ! -f "$STAGE_DIR/EmberEye/ip_loc_map.json" ]; then
    echo '{}' > "$STAGE_DIR/EmberEye/ip_loc_map.json"
fi

# Re-copy windows bundle files into staged tree (ensure paths)
mkdir -p "$STAGE_DIR/EmberEye/windows_bundle"
cp "$ROOT_DIR/windows_bundle/setup_windows_complete.bat" "$STAGE_DIR/EmberEye/windows_bundle/"
cp "$ROOT_DIR/windows_bundle/README_WINDOWS.md" "$STAGE_DIR/EmberEye/windows_bundle/"

# Create the zip
echo "[INFO] Creating ZIP at $ZIP_FILE"
(cd "$STAGE_DIR" && zip -r "$ZIP_FILE" "EmberEye" > /dev/null)

# Move zip to project root
mv "$ZIP_FILE" "$ROOT_DIR/"

echo "[SUCCESS] Bundle created: $ROOT_DIR/${BUNDLE_NAME}.zip"
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'matplotlib.pyplot', 'matplotlib.backends'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EmberEye',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',  # Windows icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EmberEye',
)
EOF

# Create batch file for icon generation on Windows
cat > "$WINDOWS_MIGRATION_DIR/create_icon_windows.bat" << 'EOF'
@echo off
REM Convert logo.png to Windows ICO format
REM Requires ImageMagick or similar tool

echo Creating Windows icon from logo.png...

REM Check if ImageMagick is available
where magick >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    magick convert logo.png -define icon:auto-resize=256,128,64,48,32,16 logo.ico
    echo Icon created: logo.ico
) else (
    echo ERROR: ImageMagick not found. Install from https://imagemagick.org/
    echo Alternative: Use online converter at https://convertio.co/png-ico/
    pause
)
EOF

# Create Windows setup batch file
cat > "$WINDOWS_MIGRATION_DIR/setup_windows.bat" << 'EOF'
@echo off
echo ==========================================
echo EmberEye Windows Setup
echo ==========================================
echo.

REM Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9 or later from https://www.python.org/
    pause
    exit /b 1
)

echo Python found.
echo.

REM Create virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ==========================================
echo Setup complete!
echo ==========================================
echo.
echo To run the application:
echo   1. Activate environment: .venv\Scripts\activate.bat
echo   2. Run: python main.py
echo.
echo To build EXE:
echo   1. Activate environment: .venv\Scripts\activate.bat
echo   2. Run: pyinstaller EmberEye_Windows.spec
echo.
pause
EOF

# Create Windows build batch file
cat > "$WINDOWS_MIGRATION_DIR/build_windows_exe.bat" << 'EOF'
@echo off
echo ==========================================
echo Building EmberEye Windows EXE
echo ==========================================
echo.

REM Activate virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run setup_windows.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Check PyInstaller
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing PyInstaller...
    pip install pyinstaller==6.16.0
)

REM Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

REM Build EXE
echo.
echo Building application...
pyinstaller EmberEye_Windows.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo Build successful!
    echo ==========================================
    echo.
    echo The application is in: dist\EmberEye\
    echo Run: dist\EmberEye\EmberEye.exe
    echo.
    echo To create installer, see WINDOWS_DEPLOYMENT.md
) else (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
pause
EOF

# Create Windows deployment guide
cat > "$WINDOWS_MIGRATION_DIR/WINDOWS_DEPLOYMENT.md" << 'EOF'
# EmberEye Windows Deployment Guide

## Prerequisites

### Required Software
1. **Python 3.9 or later**
   - Download from: https://www.python.org/downloads/
   - ✅ Check "Add Python to PATH" during installation

2. **Visual C++ Redistributable** (for users)
   - Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
   - Required for PyQt5 and OpenCV

3. **ImageMagick** (for icon creation, optional)
   - Download: https://imagemagick.org/script/download.php
   - Alternative: Use online PNG to ICO converter

## Setup Instructions

### Step 1: Extract and Setup
```batch
:: Extract the migration package
:: Navigate to the extracted folder

:: Run setup
setup_windows.bat
```

This will:
- Create Python virtual environment
- Install all dependencies
- Set up the development environment

### Step 2: Create Windows Icon
```batch
:: Option A: Using ImageMagick (if installed)
create_icon_windows.bat

:: Option B: Manual conversion
:: 1. Visit https://convertio.co/png-ico/
:: 2. Upload logo.png
:: 3. Download as logo.ico
:: 4. Place in project root
```

### Step 3: Build EXE
```batch
build_windows_exe.bat
```

The executable will be created in: `dist\EmberEye\EmberEye.exe`

## Testing the EXE

### Quick Test
```batch
cd dist\EmberEye
EmberEye.exe
```

### Verify Components
- ✅ Application launches
- ✅ Login window appears
- ✅ Logo/icon displays correctly
- ✅ TCP server starts (check port 9001)
- ✅ Can login with default credentials

## Distribution

### Option 1: Distribute Folder
1. Zip the entire `dist\EmberEye` folder
2. Users extract and run `EmberEye.exe`
3. Include `WINDOWS_USER_GUIDE.md`

### Option 2: Create Installer (Recommended)

#### Using Inno Setup (Free)
1. **Download Inno Setup**: https://jrsoftware.org/isinfo.php

2. **Create installer script** (`EmberEye_installer.iss`):
```iss
[Setup]
AppName=EmberEye
AppVersion=1.0.0
DefaultDirName={pf}\EmberEye
DefaultGroupName=EmberEye
OutputDir=installer
OutputBaseFilename=EmberEye_Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\EmberEye\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\EmberEye"; Filename: "{app}\EmberEye.exe"
Name: "{commondesktop}\EmberEye"; Filename: "{app}\EmberEye.exe"

[Run]
Filename: "{app}\EmberEye.exe"; Description: "Launch EmberEye"; Flags: postinstall nowait skipifsilent
```

3. **Compile**: Open with Inno Setup and click "Compile"

4. **Installer Output**: `installer\EmberEye_Setup.exe`

#### Using NSIS (Alternative)
1. **Download NSIS**: https://nsis.sourceforge.io/Download

2. **Create script** (`installer.nsi`):
```nsis
!define PRODUCT_NAME "EmberEye"
!define PRODUCT_VERSION "1.0.0"

Name "${PRODUCT_NAME}"
OutFile "EmberEye_Setup.exe"
InstallDir "$PROGRAMFILES\${PRODUCT_NAME}"

Section "Main"
    SetOutPath "$INSTDIR"
    File /r "dist\EmberEye\*.*"
    CreateShortcut "$DESKTOP\EmberEye.lnk" "$INSTDIR\EmberEye.exe"
    CreateShortcut "$SMPROGRAMS\EmberEye.lnk" "$INSTDIR\EmberEye.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\*.*"
    RMDir /r "$INSTDIR"
    Delete "$DESKTOP\EmberEye.lnk"
    Delete "$SMPROGRAMS\EmberEye.lnk"
SectionEnd
```

3. **Compile**: Right-click script → "Compile NSIS Script"

## Troubleshooting

### Issue: "MSVCP140.dll not found"
**Solution**: Install Visual C++ Redistributable
```
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

### Issue: Application won't start
**Solution**: Run from command prompt to see errors
```batch
cd dist\EmberEye
EmberEye.exe
```

### Issue: No icon showing
**Solution**: 
1. Verify `logo.ico` exists in project root
2. Rebuild with: `pyinstaller EmberEye_Windows.spec`

### Issue: "Failed to execute script"
**Solution**: Check console mode
1. Edit `EmberEye_Windows.spec`
2. Change `console=False` to `console=True`
3. Rebuild to see error messages

### Issue: Antivirus blocking
**Solution**: 
1. Add exclusion for EmberEye.exe
2. Sign the executable (for production)

### Issue: Slow startup
**Solution**: 
- First run is slower (Windows Defender scan)
- Add to antivirus exclusions
- Subsequent runs are faster

## Code Signing (Production)

For production distribution, sign your executable:

1. **Get Code Signing Certificate**
   - Purchase from: DigiCert, Sectigo, etc.
   - ~$200-500/year

2. **Sign the EXE**
```batch
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist\EmberEye\EmberEye.exe
```

## Default Credentials
- **Admin**: admin / password
- **User 1**: ratna / ratna
- **User 2**: s3micro / s3micro

## System Requirements
- Windows 10 or later (64-bit)
- 4GB RAM minimum
- 500MB disk space
- Camera/RTSP stream access

## Support
- Check logs in: `%USERPROFILE%\.embereye\`
- Database: `%USERPROFILE%\.embereye\users.db`
- Config: `%USERPROFILE%\.embereye\stream_config.json`

## Additional Notes

### Performance Optimization
- Exclude from Windows Defender for faster startup
- Use SSD for better performance
- Close unnecessary background applications

### Firewall Rules
The application uses:
- **TCP Port 9001**: Sensor data server
- **TCP Port 8765**: WebSocket server
- **TCP Port 554**: RTSP streams (if applicable)

### Automatic Startup
To run on Windows startup:
1. Press `Win + R`
2. Type: `shell:startup`
3. Create shortcut to `EmberEye.exe` in this folder

EOF

# Create Windows user guide
cat > "$WINDOWS_MIGRATION_DIR/WINDOWS_USER_GUIDE.md" << 'EOF'
# EmberEye User Guide (Windows)

## Installation

### First Time Setup
1. Extract `EmberEye.zip` to a folder (e.g., `C:\Program Files\EmberEye\`)
2. Run `EmberEye.exe`
3. Login with default credentials

### Running the Application
- Double-click `EmberEye.exe`
- Or create a desktop shortcut

## First Login
**Default Credentials:**
- Username: `ratna` or `s3micro`
- Password: `ratna` or `s3micro`

**Admin Access:**
- Username: `admin`
- Password: `password`

## Features

### Stream Configuration
1. Click **Settings** (gear icon)
2. Select **Stream Configuration**
3. Click **Add Stream** or **Discover Cameras**

### ONVIF Camera Discovery
1. Settings → Stream Configuration
2. Click **Discover**
3. Select scan type:
   - **ONVIF Scan**: Discover ONVIF cameras with profiles
   - **RTSP Port Scan**: Quick scan for cameras on port 554
4. Select cameras and add to configuration

### TCP Sensor Server
- **Status**: Green LED = Running, Red LED = Stopped
- **Port**: Default 9001 (configurable)
- **Restart**: Click ↻ button in status bar
- **Message Counter**: Shows incoming sensor packets

### Sensor Configuration
Settings → Sensor Configuration
- Temperature threshold
- Gas PPM threshold
- Flame detection settings
- Grid cell decay time

### Thermal Grid Settings
Settings → Thermal Grid Settings
- Enable/disable overlay
- Grid dimensions (rows × columns)
- Colors and border width

### Baseline Management
- **Capture**: Click camera icon on video widget
- **View Events**: Check baseline_events.json
- **Clear**: Reset thermal baselines

## Troubleshooting

### Application Won't Start
1. Check if Visual C++ Redistributable is installed
2. Run from Command Prompt to see errors
3. Check antivirus isn't blocking

### Camera Not Connecting
1. Verify camera is online (ping IP address)
2. Test RTSP URL in VLC player
3. Check firewall settings
4. Ensure camera credentials are correct

### TCP Server Port Conflict
1. Click ↻ Restart button in status bar
2. Change to different port (e.g., 9002)
3. Update sensor devices with new port

### Performance Issues
1. Close other applications
2. Reduce number of active streams
3. Lower thermal grid resolution
4. Check CPU/RAM usage

## Data Locations

### User Data
```
C:\Users\<YourName>\.embereye\
├── users.db              # User database
├── stream_config.json    # Camera configuration
└── baseline_events.json  # Thermal events
```

### Logs
Check application folder for error logs

## Keyboard Shortcuts
- **F11**: Toggle fullscreen (video widget)
- **ESC**: Exit fullscreen
- **Ctrl+Q**: Quit application

## Network Configuration

### Required Ports
- **9001**: TCP sensor server (incoming)
- **8765**: WebSocket server
- **554**: RTSP camera streams (outgoing)

### Firewall Rules
Add inbound rule for TCP port 9001 if using external sensors

## Support
For technical support, contact your system administrator.

EOF

# Create requirements.txt for Windows
cat > "$WINDOWS_MIGRATION_DIR/requirements.txt" << 'EOF'
PyQt5>=5.15.0
opencv-python>=4.8.0
numpy>=1.24.0
bcrypt>=4.0.0
websockets>=12.0
psutil>=5.9.0
onvif-zeep>=0.2.12
wsdiscovery>=2.0.0
Pillow>=10.0.0
EOF

# Create README for Windows migration
cat > "$WINDOWS_MIGRATION_DIR/README_WINDOWS.md" << 'EOF'
# EmberEye Windows Migration Package

This package contains everything needed to deploy EmberEye on Windows.

## Quick Start

1. **Setup Environment**
   ```batch
   setup_windows.bat
   ```

2. **Create Icon** (Optional)
   ```batch
   create_icon_windows.bat
   ```
   Or use online converter for logo.png → logo.ico

3. **Build EXE**
   ```batch
   build_windows_exe.bat
   ```

4. **Test Application**
   ```batch
   cd dist\EmberEye
   EmberEye.exe
   ```

## Files Included
- ✅ Complete source code
- ✅ Windows-specific PyInstaller spec
- ✅ Setup scripts (batch files)
- ✅ Build automation
- ✅ Deployment documentation
- ✅ User guide

## Documentation
- `WINDOWS_DEPLOYMENT.md` - Complete deployment guide
- `WINDOWS_USER_GUIDE.md` - End-user instructions
- `EmberEye_Windows.spec` - PyInstaller configuration

## System Requirements
- Windows 10/11 (64-bit)
- Python 3.9+ (for development)
- 4GB RAM
- 500MB disk space

## Default Credentials
- ratna / ratna
- s3micro / s3micro
- admin / password

## Support
See WINDOWS_DEPLOYMENT.md for troubleshooting.
EOF

# Create VERSION file
cat > "$WINDOWS_MIGRATION_DIR/VERSION.txt" << EOF
EmberEye v1.0.0 - Windows Edition
Build Date: $(date)
Migration Package: $TIMESTAMP

Platform: Windows 10/11 (64-bit)
Python: 3.9+

Features:
- RTSP stream monitoring
- Fire/smoke detection with OpenCV
- Multi-sensor fusion
- TCP sensor server (port 9001)
- ONVIF camera discovery
- User authentication (bcrypt)
- Thermal baseline management

TCP Status Indicator:
- Green LED = Server running
- Red LED = Server stopped
- Message counter
- Port configuration with restart

Distribution:
- Standalone EXE (no Python required)
- Installer ready (Inno Setup/NSIS)
- Code signing ready
EOF

# Create ZIP package
echo ""
echo "Creating Windows migration archive..."
zip -r "${WINDOWS_MIGRATION_DIR}.zip" "$WINDOWS_MIGRATION_DIR" -q

# Calculate size
SIZE=$(du -h "${WINDOWS_MIGRATION_DIR}.zip" | cut -f1)

echo ""
echo "============================================"
echo "Windows Migration Package Created!"
echo "============================================"
echo ""
echo "Archive: ${WINDOWS_MIGRATION_DIR}.zip"
echo "Size: $SIZE"
echo ""
echo "Contents:"
echo "  ✅ Complete source code"
echo "  ✅ Windows PyInstaller spec"
echo "  ✅ Setup batch files"
echo "  ✅ Build automation"
echo "  ✅ Deployment guides"
echo "  ✅ User documentation"
echo ""
echo "Transfer to Windows:"
echo "  1. Copy ${WINDOWS_MIGRATION_DIR}.zip to Windows PC"
echo "  2. Extract the ZIP file"
echo "  3. Run setup_windows.bat"
echo "  4. Run build_windows_exe.bat"
echo ""
echo "Output: dist\\EmberEye\\EmberEye.exe"
echo ""
echo "Cleanup:"
echo "  rm -rf $WINDOWS_MIGRATION_DIR  # Remove folder"
echo ""
