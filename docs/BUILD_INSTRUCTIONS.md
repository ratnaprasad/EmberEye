# EmberEye Windows Executable Build Instructions

## Prerequisites

1. **Python 3.8 or higher** installed on Windows
2. **PyInstaller** package
3. All project dependencies from `requirements.txt`

## Step-by-Step Instructions

### 1. Extract the Source Files

Extract `EmberEye_Windows_Source_20251130.zip` to a folder on your Windows machine, e.g.:
```
C:\EmberEye\
```

### 2. Open Command Prompt

Press `Win + R`, type `cmd`, and press Enter.

Navigate to the EmberEye folder:
```cmd
cd C:\EmberEye
```

### 3. Create a Virtual Environment (Recommended)

```cmd
python -m venv venv
venv\Scripts\activate
```

### 4. Install Dependencies

```cmd
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

### 5. Build the Executable

#### Option A: Using the Existing Spec File (Recommended)

```cmd
pyinstaller EmberEye.spec
```

#### Option B: Manual Build Command

```cmd
pyinstaller --name=EmberEye ^
    --windowed ^
    --onefile ^
    --icon=logo.png ^
    --add-data "images;images" ^
    --add-data "stream_config.json;." ^
    --add-data "logo.png;." ^
    --hidden-import=PyQt5.QtCore ^
    --hidden-import=PyQt5.QtGui ^
    --hidden-import=PyQt5.QtWidgets ^
    main.py
```

### 6. Locate the Executable

After successful build, the executable will be in:
```
C:\EmberEye\dist\EmberEye.exe
```

### 7. Test the Executable

```cmd
cd dist
EmberEye.exe
```

## Build Output Structure

```
EmberEye\
├── dist\
│   └── EmberEye.exe          ← Your standalone executable
├── build\                     ← Temporary build files (can be deleted)
└── EmberEye.spec             ← Build configuration
```

## Troubleshooting

### Issue: "PyInstaller not found"
**Solution:** Install PyInstaller:
```cmd
pip install pyinstaller
```

### Issue: "ModuleNotFoundError" during execution
**Solution:** Add missing module to spec file:
```python
# In EmberEye.spec, add to hiddenimports list:
hiddenimports=['missing_module_name']
```

### Issue: Missing images/icons in executable
**Solution:** Ensure `--add-data` includes all resource folders:
```cmd
--add-data "images;images"
--add-data "stream_config.json;."
```

### Issue: Executable is too large
**Solution:** Use `--onedir` instead of `--onefile`:
```cmd
pyinstaller EmberEye.spec --onedir
```
This creates a folder with the executable and dependencies (faster startup, smaller file).

### Issue: Antivirus blocks the executable
**Solution:** 
- Add exception in Windows Defender/antivirus
- Sign the executable with a code signing certificate (for production)

## Distribution

To distribute the application:

1. **Single File (Portable):**
   - Just copy `EmberEye.exe` from `dist\` folder
   - Users can run it directly without installation

2. **Installer Package (Recommended):**
   - Use [Inno Setup](https://jrsoftware.org/isinfo.php) or [NSIS](https://nsis.sourceforge.io/)
   - Create a proper Windows installer
   - Include uninstaller and Start Menu shortcuts

## Advanced: Creating an Installer with Inno Setup

1. Download and install [Inno Setup](https://jrsoftware.org/isdl.php)

2. Create `EmberEye.iss` file:
```inno
[Setup]
AppName=EmberEye
AppVersion=1.0
DefaultDirName={pf}\EmberEye
DefaultGroupName=EmberEye
OutputDir=installer
OutputBaseFilename=EmberEye_Setup

[Files]
Source: "dist\EmberEye.exe"; DestDir: "{app}"
Source: "images\*"; DestDir: "{app}\images"
Source: "stream_config.json"; DestDir: "{app}"

[Icons]
Name: "{group}\EmberEye"; Filename: "{app}\EmberEye.exe"
Name: "{commondesktop}\EmberEye"; Filename: "{app}\EmberEye.exe"
```

3. Compile with Inno Setup:
   - Right-click `EmberEye.iss` → "Compile"
   - Installer will be in `installer\EmberEye_Setup.exe`

## Notes

- **First run may be slow**: PyInstaller executables extract to temp folder on first launch
- **File size**: Expect 80-150 MB for bundled executable (includes Python runtime + all dependencies)
- **Compatibility**: Built on Windows 10/11, compatible with Windows 7 SP1+
- **Updates**: Rebuild executable after any source code changes

## Quick Build Script

Create `build.bat` for automated builds:
```bat
@echo off
echo Building EmberEye executable...
call venv\Scripts\activate
pyinstaller EmberEye.spec --clean
echo.
echo Build complete! Executable is in dist\EmberEye.exe
pause
```

Run: `build.bat`

---

**For macOS/Linux executables**, follow similar steps but use platform-specific PyInstaller commands and spec files.
